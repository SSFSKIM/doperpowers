import type { EngineInterface, HookStream, TurnStepChunk, TurnStepInput, TurnStepResult } from 'claude-code'

import type { HolderKept, ReceiptReport, StoppedReceipt } from '../../types/sminos'

import { REPORTS_KEPT, admitCarried, holdReleases, liveMarks, releaseStoppedNow, reportAnswered, scanConversation, stopCarried, turnDelivery } from './bridge-receipts'
import type { Carried } from './bridge-receipts'
import { isRecord, message, parsed, state } from './bridge-state'
import type { FencedStep, HolderAsked, HolderFence, HolderRelay, HolderState, PromptSeen, TurnOrigin } from './bridge-state'

/**
 * The lane B observer's fence (O12 M4a): MAWS's engine host reaps an idle
 * lane B session only once its observer has installed the host's arm and
 * acknowledged it, and asks of every main-loop model request whether it may
 * go (OX10, O16 Interfaces §E as its fix wave corrected it). The bridge's
 * child owns the gate's socket (skills/sminos/scripts/sminos_holder.py, whose
 * docstring is the relay's contract); this module owns the fence:
 *
 * - The child's bootstrap line names its private route; the module keeps
 *   `observerStarted` in `$.state` and then tells the child it is ready, so
 *   the gate's first hello follows a kept commitment.
 * - Each relayed arm is installed at once, before any await: its fence held
 *   from then until the host's `disarm`, or its lease plus the heartbeat
 *   margin by `$.clock.after` from its receipt (never `$.clock.now()`, a wall
 *   clock), the latest arm of a fence alone able to end it. The fences are
 *   kept in `$.state`, then each arm is acknowledged once, in the order the
 *   arms came (R1); while a main turn runs, its `turn` goes first, so the
 *   host never reads an acknowledgement as leave to reap a turn it was not
 *   told of.
 * - A main-loop request with any fence installed asks `turn` of each and
 *   waits: every fence must release it (`proceed`, `disarm` or its expiry),
 *   and one `stop` ends the turn without a request. A reconnect, a new child
 *   or a new epoch's `proceed` releases nothing of an older epoch's fence.
 * - Each arm is acknowledged only once its fence is kept and its `turn`, if
 *   one was owed, is written; what failed is tried again, never skipped, so
 *   the arms after it are never acknowledged ahead of it.
 * - A module that loads into the process (a reload) holds the kept fences
 *   before any request can pass, each for one full lease and margin from
 *   then: the time already spent cannot be read without a wall clock. A kept
 *   state it cannot read holds every main request for the production lease
 *   and margin, once (C3).
 * - A turn's origin is the engine's stamp on the prompt that started it,
 *   seen at `prompt.submit` and in its row, matched to the turn by text
 *   among the prompts seen before it started; a prompt delivered into a
 *   running turn is no turn's evidence. `unknown` when nothing matches, or
 *   when prompts of its text disagree. It is diagnostic: every origin is
 *   fenced alike.
 *
 * Receipts (O12 M4b; bridge-receipts.tsx decides which a request carries):
 *
 * - The child's first ready asks it to activate receipts for this process
 *   before its first hello, on positive evidence that the process is a
 *   fresh one: this module handled the process's own classic SessionStart
 *   (`startup`, `resume`, `fork`: the engine raises it as the process
 *   starts its session, never at a plugin reload or a worker respawn, and a
 *   /clear's or a compaction's is no start) with no trace of a module before
 *   it (a kept launch, kept holder state), or a module before this one found
 *   it so (`fresh`, kept). Then with the process's launch and the receipts
 *   the live conversation holds (`retained`). Any other process is an
 *   existing one, its absent bookkeeping no evidence that nothing was
 *   handed off: an upgrade the child records `legacy`, observed if an
 *   observer served it before (an M4a observer goes on), never observed
 *   otherwise (no hello: the host keeps its lineage registration). A first
 *   bootstrap with no evidence either way waits STARTUP_WAIT_MS for the
 *   SessionStart (the engine runs it while the first session.start is
 *   still settling), then takes the process for an existing one. The
 *   child's `processAge` is said for diagnosis; it decides nothing.
 * - A main-loop request the module admits (a `proceed`, no fence, a lease's
 *   expiry) reports the receipts it carries, decided with no await before
 *   its `next`; the report is kept in `$.state` and replayed on the child's
 *   route until the child answers it recorded, whatever the stream does. A
 *   request the gate stopped reports nothing; its receipts are released for
 *   a retry in this launch once no fence holds (the matching disarm, every
 *   lease and margin run out), never on a welcome alone.
 * - A main turn whose own text carries a receipt names it in its `turn`
 *   (`delivery`, the first of several).
 */

/**
 * How long a first bootstrap with no evidence of the process's start waits
 * for its SessionStart before the process is taken for an existing one (O12
 * M4b): the engine raises it beside the first session.start, which spawns
 * the child, so on a start it is there at once or within moments; a module
 * reloaded into a running process waits this long once, before its hello.
 */
export const STARTUP_WAIT_MS = 5_000

/** The observer's fallback past a lease: one heartbeat, OX10's production margin. */
export const HOLDER_MARGIN_MS = 5_000
/** How long one held wait on the child's route lasts while a request waits at the fence: a call in flight stops the hook's own budget. */
export const HOLDER_WAIT_MS = 5_000
/** How soon an acknowledgement that failed for want of the kept state or the child is tried again. */
export const HOLDER_RETRY_MS = 1_500
/** OX10's production lease: the lease of a kept state this module cannot read (C3). */
const PRODUCTION_LEASE_MS = 10_000
/** The fence that stands for a kept state this module could not read: no child's epoch, so no gate's frame names it. */
const UNREAD = { epoch: 'unread', fence: 0 } as const
/** What a stopped request says when the host's `stop` carried no reason. */
export const HOLDER_STOP_REASON = 'The holder ended this session; reopening it continues the conversation.'
/** A POST the route did not answer (the child ending): tried this many times while its relay stands. */
const POST_TRIES = 3
/** Prompts seen and not yet matched to a turn, and main turns tracked, at most. */
const PROMPTS_KEPT = 32
const TURNS_KEPT = 16
/** The longest lease a timer can hold: `$.clock.after` past 2^31 - 1 ms would fire at once. */
const LEASE_MAX_MS = 2_147_483_647 - HOLDER_MARGIN_MS
const HOLDER = { plugin: 'sminos', key: 'holder' } as const
/**
 * The engine's prompt origins (PromptOrigin) as OX10's turn origins; any
 * other is `unknown`. `composer` is what the engine stamps on a prompt MAWS's
 * host writes on stdin (C4): the controller's own prompt, a query.
 */
const ORIGINS: Record<string, TurnOrigin> = { composer: 'query', sdk: 'query', 'scheduled-trigger': 'cron', 'task-notification': 'task', peer: 'peer', 'peer-send-message': 'peer' }

export const fenceKey = (epoch: string, fence: number) => `${epoch}#${fence}`
const isCount = (v: unknown, least = 0): v is number => typeof v === 'number' && Number.isInteger(v) && v >= least
const isLease = (v: unknown): v is number => isCount(v, 1) && v <= LEASE_MAX_MS
const log = (text: string) => state.log?.(`bridge: holder: ${text}`)

// -- what the process keeps

const isId = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{24}\.[0-9a-f]{16}$/.test(v)
const isSession = (v: unknown): v is string => typeof v === 'string' && v !== '' && v.length <= 64

function isReport(r: unknown): r is ReceiptReport {
  return (
    isRecord(r) &&
    isSession(r.session) &&
    ((r.kind === 'admit' && Array.isArray(r.ids) && r.ids.length > 0 && r.ids.every(isId)) ||
      (r.kind === 'release' && Array.isArray(r.items) && r.items.length > 0 && r.items.every((i) => isRecord(i) && isId(i.id) && isCount(i.attempt, 1) && typeof i.present === 'boolean')))
  )
}

const isStopped = (s: unknown): s is StoppedReceipt => isRecord(s) && isSession(s.session) && isId(s.id) && isCount(s.attempt, 1)

function isKept(value: unknown): value is HolderKept {
  return (
    isRecord(value) &&
    value.shape === 1 &&
    typeof value.observerStarted === 'boolean' &&
    isCount(value.armGenerations) &&
    Array.isArray(value.fences) &&
    value.fences.every((f) => isRecord(f) && typeof f.epoch === 'string' && isCount(f.fence) && isCount(f.armGeneration) && isLease(f.leaseMs)) &&
    (value.receipts === undefined || (isRecord(value.receipts) && Array.isArray(value.receipts.reports) && value.receipts.reports.every(isReport) && Array.isArray(value.receipts.stopped) && value.receipts.stopped.every(isStopped))) &&
    (value.fresh === undefined || typeof value.fresh === 'boolean')
  )
}

const snapshot = (h: HolderState): HolderKept => ({
  shape: 1,
  owner: h.owner,
  observerStarted: h.observerStarted,
  armGenerations: h.armGenerations,
  fences: [...h.fences.values()].map((f) => ({ epoch: f.epoch, fence: f.fence, armGeneration: f.armGeneration, leaseMs: f.leaseMs })),
  receipts: { reports: h.receipts.reports, stopped: h.receipts.stopped },
  ...(h.fresh !== undefined && { fresh: h.fresh }),
})

/**
 * Writes what this module holds, after every write before it and once the
 * kept state is restored: true once written.
 *
 * The kept state has one writer at a time: a hot reload unloads the old
 * module's environment before the new one loads (measured on 2.1.316, O12
 * M4a review fix 2: the old instance's timers and in-flight `$` calls are
 * rejected at the unload and every later `$` call is refused, so it can
 * neither keep nor acknowledge; its bridge child is killed within about
 * 0.1 s, closing its gate connection before the new child's hello).
 */
function keep($: EngineInterface): Promise<boolean> {
  const h = state.holder
  const write = h.writes.then(() => h.loaded).then(() => keepNow($, h))
  h.writes = write
  return write
}

async function keepNow($: EngineInterface, h: HolderState): Promise<boolean> {
  if (h !== state.holder) {
    return false
  }
  try {
    await $.state.set(HOLDER, snapshot(h))
    return true
  } catch (error) {
    log(`the fences are not kept: ${message(error)}`)
    return false
  }
}

/**
 * Restores what the module before this one kept (a reload), once and before
 * any main request passes: each kept fence held again for a whole lease and
 * margin from now, `observerStarted` as it was. A kept state this module
 * cannot read, or cannot read at all, is held as one fence of the production
 * lease (C3): any lease the host confirmed before the reload ends within it,
 * and an arm after the reload is installed afresh. The window runs once:
 * nothing kept before the reload is held after it.
 */
export function holderLoaded($: EngineInterface): Promise<void> {
  const h = state.holder
  h.load ??= restore($, h).finally(() => {
    h.isLoaded = true
    h.markLoaded()
    if (h === state.holder) {
      wakeStep()
    }
  })
  return h.load
}

/** Whether the kept state was restored already: a request then needs no await for it. */
export const isHolderLoaded = () => state.holder.isLoaded

/**
 * A session no gate serves (no marker, or one this process controls) has
 * nothing to restore. What a module before this one left says whether the
 * process is a fresh one (O12 M4b): the `fresh` it decided; or, with none,
 * an existing one (an M4a module's state, a launch kept with no holder
 * state, a state it cannot read). Nothing at all left decides nothing: the
 * process's own SessionStart, or its absence, does at the first bootstrap.
 */
async function restore($: EngineInterface, h: HolderState): Promise<void> {
  let kept: unknown
  try {
    if ((await $.env.get('MAWS_LANE')) !== 'B' || state.laneVerdict === 'mismatch') {
      return
    }
    kept = (await $.state.get(HOLDER)).value
  } catch (error) {
    holdUnread($, h, `the kept state is not read: ${message(error)}`)
    return
  }
  if (kept === undefined) {
    if (state.launchFrom !== 'new') {
      h.fresh = false
    }
    return
  }
  if (!isKept(kept)) {
    holdUnread($, h, 'the kept state is not one this module reads')
    return
  }
  h.fresh = kept.fresh === true
  if (kept.receipts !== undefined) {
    h.receipts.reports.push(...kept.receipts.reports.slice(-REPORTS_KEPT))
    h.receipts.stopped.push(...kept.receipts.stopped)
  }
  h.observerStarted ||= kept.observerStarted
  h.armGenerations = Math.max(h.armGenerations, kept.armGenerations)
  for (const f of kept.fences) {
    install($, f.epoch, f.fence, f.leaseMs)
  }
  if (kept.fences.length > 0) {
    log(`${kept.fences.length} fence(s) held again for a whole lease and margin`)
  }
}

/**
 * What this module could not read of the kept state, held as one fence of
 * the production lease from now (C3): no gate's, so no answer ends it, only
 * its lease and margin. `observerStarted` is taken as kept: never taken
 * back, and what could not be read may have said so.
 */
function holdUnread($: EngineInterface, h: HolderState, why: string) {
  if (h !== state.holder) {
    return
  }
  h.observerStarted = true
  // What it kept of receipts is lost too: an existing process, observed.
  h.fresh = false
  install($, UNREAD.epoch, UNREAD.fence, PRODUCTION_LEASE_MS)
  log(`${why}: main requests are held ${PRODUCTION_LEASE_MS + HOLDER_MARGIN_MS} ms from now (one production lease and margin), then admitted`)
}

// -- the fences

/** Installs an arm of a fence (its first or a renewal): held from now for its lease and the margin, unless a later arm or a disarm comes. */
function install($: EngineInterface, epoch: string, fence: number, leaseMs: number) {
  const h = state.holder
  const key = fenceKey(epoch, fence)
  const f: HolderFence = h.fences.get(key) ?? { epoch, fence, armGeneration: 0, leaseMs }
  f.timer?.cancel()
  f.armGeneration = ++h.armGenerations
  f.leaseMs = leaseMs
  const generation = f.armGeneration
  f.timer = $.clock.after(leaseMs + HOLDER_MARGIN_MS, () => expire($, f, generation))
  h.fences.set(key, f)
  wakeStep()
}

/** The latest arm's lease and margin passed with no answer: its fence lets requests go. An earlier arm's timer, or another module's, ends nothing. */
function expire($: EngineInterface, f: HolderFence, generation: number) {
  const h = state.holder
  const key = fenceKey(f.epoch, f.fence)
  if (h.fences.get(key) !== f || f.armGeneration !== generation) {
    return
  }
  h.fences.delete(key)
  log(`fence ${key}: no answer within its lease and the margin`)
  void keep($)
  wakeStep()
  void releaseStopped()
}

function release($: EngineInterface, key: string) {
  const h = state.holder
  const f = h.fences.get(key)
  if (f === undefined) {
    return
  }
  f.timer?.cancel()
  h.fences.delete(key)
  void keep($)
  wakeStep()
  void releaseStopped()
}

const wakeStep = () => state.holder.step?.wake?.()

/** Whether a main turn is running, or may be (a module loaded while one ran): an arm then tells the host the turn before acknowledging. */
const isMainActive = () => state.holder.step !== undefined || state.mainTurn !== undefined || state.isTurnUnknown

// -- the child's lines

/**
 * A `holder` line of the current child (bridge.tsx has checked it is the
 * current child's and carries no command id): its bootstrap, or a host frame
 * it relays under the connection's epoch.
 */
export function onHolderLine($: EngineInterface, msg: Record<string, unknown>) {
  const h = state.holder
  if (isRecord(msg.bootstrap)) {
    void takeBootstrap($, msg.bootstrap)
    return
  }
  const relay = h.relay
  const { epoch, frame } = msg
  if (relay === undefined || !isCurrent(relay) || typeof epoch !== 'string' || !epoch.startsWith(`${relay.generation}.`) || !isRecord(frame)) {
    log(`a relay line that is not this child's: ${JSON.stringify(msg).slice(0, 200)}`)
    return
  }
  const fence = frame.fence
  if (frame.t === 'welcome') {
    relay.epoch = epoch
    log(`welcomed (epoch ${epoch})`)
    return
  }
  if (!isCount(fence)) {
    log(`a relayed frame with no fence: ${JSON.stringify(frame).slice(0, 200)}`)
    return
  }
  const key = fenceKey(epoch, fence)
  switch (frame.t) {
    case 'arm':
      if (!isCount(msg.arm, 1) || !isLease(frame.leaseMs)) {
        log(`an arm this module cannot hold: ${JSON.stringify(msg).slice(0, 200)}`)
        return
      }
      onArm($, relay, epoch, msg.arm, fence, frame.leaseMs)
      return
    case 'disarm':
      release($, key)
      return
    case 'proceed':
      answer(key, {})
      return
    case 'stop':
      answer(key, { stop: typeof frame.reason === 'string' && frame.reason !== '' ? frame.reason : HOLDER_STOP_REASON })
      return
  }
}

const isCurrent = (relay: HolderRelay) => state.holder.relay === relay && relay.child === state.generation

async function takeBootstrap($: EngineInterface, b: Record<string, unknown>) {
  // A session this process controls never has a gate.
  if (!state.isLaneMarked || state.laneVerdict === 'mismatch') {
    return
  }
  const pid = (v: unknown) => (isCount(v, 1) ? v : null)
  if (typeof b.socket !== 'string' || typeof b.nonce !== 'string' || typeof b.generation !== 'string' || b.generation === '') {
    log(`a bootstrap with no route: ${JSON.stringify(b).slice(0, 200)}`)
    return
  }
  const h = state.holder
  const relay: HolderRelay = { socket: b.socket, nonce: b.nonce, generation: b.generation, pid: pid(b.pid), childPid: pid(b.childPid), child: state.generation }
  h.relay = relay
  h.engine = $
  // What a module before this one kept is in before anything is written.
  await h.loaded
  // A fresh process, or an existing one (O12 M4b): decided once per process.
  if (h.fresh === undefined && !h.isProcessStart) {
    await new Promise<void>((resolve) => {
      h.onProcessStart = resolve
      $.clock.after(STARTUP_WAIT_MS, resolve)
    })
    h.onProcessStart = undefined
  }
  if (h.fresh === undefined) {
    h.fresh = h.isProcessStart
    log(`the process is ${h.fresh ? 'a fresh one: this module handled its SessionStart' : 'an existing one: no SessionStart of its own came'} (its age ${String(b.processAge)} s)`)
  }
  if (!isCurrent(relay)) {
    return
  }
  // An existing process no observer served stays unobserved.
  const observe = h.fresh || h.observerStarted
  h.observerStarted = observe
  while (!(await keep($))) {
    if (!isCurrent(relay)) {
      return
    }
    log(`observerStarted is not kept: the gate waits, tried again in ${HOLDER_RETRY_MS} ms`)
    await new Promise<void>((resolve) => $.clock.after(HOLDER_RETRY_MS, resolve))
  }
  // The receipts the conversation holds already (a resume's retained rows).
  await scanConversation($)
  if (!isCurrent(relay)) {
    return
  }
  const activation = !h.fresh ? { upgrade: true, observe } : state.launch !== undefined ? { launch: state.launch, retained: h.receipts.retained } : {}
  const ready = await post($, relay, { kind: 'ready', ...activation })
  log(ready?.status === 200 ? `ready (child ${relay.childPid ?? '?'}, lane ${String(ready.answer?.lane)})` : `the child did not take ready (${ready?.status ?? 'no answer'})`)
  // A request waiting at the fence holds its wait on this route from now.
  wakeStep()
  // What the child before this one did not acknowledge goes to this one.
  void pumpReports()
  void releaseStopped()
}

function onArm($: EngineInterface, relay: HolderRelay, epoch: string, arm: number, fence: number, leaseMs: number) {
  const h = state.holder
  install($, epoch, fence, leaseMs)
  // While a main turn runs, its `turn` is asked at once, ahead of this ack.
  const told = isMainActive() ? askTurn($, epoch, fence) : undefined
  h.acks = h.acks.then(() => acknowledge($, h, relay, { epoch, arm, fence }, told))
}

/**
 * Acknowledges the oldest arm not yet acknowledged (R1), once its fence is
 * kept and the `turn` it owed, if a main turn ran when it came, is written.
 * What failed for want of the kept state or an answer is tried again after
 * HOLDER_RETRY_MS, the arms after it waiting behind it: the child writes an
 * `armed` only once every earlier one is in, so a skipped arm would hold
 * every later one back for good. It ends when its connection did (the
 * child's 409, a new child).
 */
async function acknowledge($: EngineInterface, h: HolderState, relay: HolderRelay, a: { epoch: string; arm: number; fence: number }, told: Promise<HolderAsked> | undefined) {
  const what = `arm ${a.arm} of ${a.epoch}`
  const isGone = () => h !== state.holder || !isCurrent(relay)
  for (let isRetry = false; ; isRetry = true) {
    if (isRetry) {
      log(`${what} is not acknowledged yet: tried again in ${HOLDER_RETRY_MS} ms`)
      await new Promise<void>((resolve) => $.clock.after(HOLDER_RETRY_MS, resolve))
      // A turn not written is asked again, while a main turn still runs.
      if (told !== undefined && (await told) === 'failed') {
        told = isMainActive() ? askTurn($, a.epoch, a.fence) : undefined
      }
    }
    if (isGone()) {
      log(`${what} is not acknowledged: this module or its child was replaced`)
      return
    }
    if ((await tryAcknowledge($, h, relay, a, told)) !== 'failed') {
      return
    }
  }
}

async function tryAcknowledge($: EngineInterface, h: HolderState, relay: HolderRelay, a: { epoch: string; arm: number; fence: number }, told: Promise<HolderAsked> | undefined): Promise<HolderAsked> {
  if (!(await keep($))) {
    return 'failed'
  }
  const turn = told === undefined ? 'written' : await told
  if (turn !== 'written') {
    if (turn === 'moot') {
      log(`arm ${a.arm} of ${a.epoch} is not acknowledged: its turn can never be written`)
    }
    return turn
  }
  const acked = await post($, relay, { kind: 'armed', ...a })
  if (acked === undefined) {
    return 'failed'
  }
  if (acked.status !== 200) {
    log(`arm ${a.arm} of ${a.epoch} is not acknowledged (${acked.status}): its connection is gone`)
    return 'moot'
  }
  return 'written'
}

function answer(key: string, a: { stop?: string }) {
  const step = state.holder.step
  if (step === undefined || !step.turns.has(key)) {
    return
  }
  step.answers.set(key, a)
  step.wake?.()
}

/** POST /holder on the child's route, naming its generation; undefined when the child never answered. */
async function post($: EngineInterface, relay: HolderRelay, body: Record<string, unknown>, attempts = POST_TRIES): Promise<{ status: number; answer?: Record<string, unknown> } | undefined> {
  let failure: unknown
  for (let tries = 0; tries < attempts && isCurrent(relay); tries++) {
    try {
      const res = await $.http.fetch('http://holder/holder', {
        method: 'POST',
        socketPath: relay.socket,
        headers: { 'content-type': 'application/json', 'x-bridge-nonce': relay.nonce },
        body: JSON.stringify({ ...body, generation: relay.generation }),
      })
      return { status: res.status, answer: parsed(res.text) }
    } catch (error) {
      failure = error
    }
  }
  if (failure !== undefined) {
    log(`POST /holder ${String(body.kind)}: ${message(failure)}`)
  }
  return undefined
}

// -- the main loop's requests

/**
 * The `turn` asked of a fence for the main turn running: once per request
 * and fence (the one already asked is the one awaited, unless it failed,
 * which is asked again). An earlier child's epoch has no connection to ask on.
 */
function askTurn($: EngineInterface, epoch: string, fence: number): Promise<HolderAsked> {
  const h = state.holder
  const key = fenceKey(epoch, fence)
  const step = h.step
  const asked = step?.turns.get(key)
  if (asked !== undefined) {
    return asked
  }
  const turnId = step?.turnId ?? state.mainTurn
  const origin = originOf(turnId)
  const delivery = turnDelivery(turnId)
  const relay = h.relay
  const turn: Promise<HolderAsked> =
    relay === undefined || !epoch.startsWith(`${relay.generation}.`)
      ? Promise.resolve('moot')
      : post($, relay, { kind: 'turn', epoch, fence, origin, ...(delivery !== undefined && { delivery }) }).then((r) => (r === undefined ? 'failed' : r.status === 200 ? 'written' : 'moot'))
  if (step !== undefined) {
    step.turns.set(key, turn)
    void turn.then((t) => {
      if (t === 'failed' && step.turns.get(key) === turn) {
        step.turns.delete(key)
      }
    })
  }
  return turn
}

/** A main-loop request entering: from now an arm tells the host of its turn before acknowledging. */
export function enterStep(turnId: string): FencedStep {
  const step: FencedStep = { turnId, entered: ++state.holder.seq, turns: new Map(), answers: new Map() }
  state.holder.step = step
  return step
}

export function leaveStep(step: FencedStep) {
  if (state.holder.step === step) {
    state.holder.step = undefined
  }
}

/**
 * Whether the request may go now, read at once and with no await, so nothing
 * comes between this and its `next`: `stop` once any fence answered it;
 * `wait` while the kept state is not restored, or an installed fence has not
 * released it; else `clear`.
 */
export function admission(step: FencedStep): 'clear' | 'wait' | { stop: string } {
  for (const a of step.answers.values()) {
    if (a.stop !== undefined) {
      return { stop: a.stop }
    }
  }
  if (!state.holder.isLoaded) {
    return 'wait'
  }
  for (const key of state.holder.fences.keys()) {
    if (!step.answers.has(key)) {
      return 'wait'
    }
  }
  return 'clear'
}

/**
 * One wait at the fence: the kept state restored if it is not yet (then the
 * request reads its fences anew), `turn` asked of every fence not yet asked,
 * then until anything moves (an answer, an arm, a disarm, an expiry, a new
 * route, the request abandoned). A wait held on the
 * child's route keeps a call in flight meanwhile, which stops the hook's own
 * budget (a hook's time, `$.clock.sleep` included, runs only while no `$`
 * call is in flight); with no route, the wait spends that budget.
 */
export async function waitAtFence($: EngineInterface, step: FencedStep, signal: AbortSignal | undefined): Promise<void> {
  const h = state.holder
  if (!h.isLoaded) {
    await holderLoaded($)
    return
  }
  for (const f of h.fences.values()) {
    void askTurn($, f.epoch, f.fence)
  }
  const woken = new Promise<void>((resolve) => {
    step.wake = resolve
    signal?.addEventListener('abort', () => resolve(), { once: true })
  })
  const relay = h.relay
  const held = relay !== undefined && isCurrent(relay) ? post($, relay, { kind: 'wait', ms: HOLDER_WAIT_MS }).then((r) => r?.status === 200) : Promise.resolve(false)
  await Promise.race([woken, held.then((isHeld) => (isHeld ? undefined : woken))])
  step.wake = undefined
}

/** The request the host's `stop` ended: no model request, the reason as its one text, then an `end_turn` stop. */
export function stoppedStep(e: TurnStepInput, reason: string): HookStream<TurnStepChunk, TurnStepResult> {
  const result: TurnStepResult = { turnId: e.turnId, index: e.index, answer: reason, toolUses: [], stopReason: 'end_turn', usage: null }
  const stream = (async function* (): AsyncGenerator<TurnStepChunk, TurnStepResult> {
    yield { kind: 'text', index: 0, text: reason }
    yield { kind: 'stop', stopReason: 'end_turn', usage: null }
    return result
  })()
  return Object.assign(stream, { result: Promise.resolve(result) })
}

/** A request abandoned while it waited at the fence (the turn cancelled): nothing streamed, no request made. */
export function abandonedStep(e: TurnStepInput): HookStream<TurnStepChunk, TurnStepResult> {
  const result: TurnStepResult = { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: null, usage: null }
  const stream = (async function* (): AsyncGenerator<TurnStepChunk, TurnStepResult> {
    return result
  })()
  return Object.assign(stream, { result: Promise.resolve(result) })
}

// -- receipts (O12 M4b)

/** The classic SessionStart: a start, a resume or a fork is the process's own (its first load's evidence); a /clear's or a compaction's is none. */
export function sessionStarted(source: string) {
  const h = state.holder
  if (source === 'startup' || source === 'resume' || source === 'fork') {
    h.isProcessStart = true
    h.onProcessStart?.()
  }
}

/**
 * The module's final admission of a main-loop request carrying these
 * receipts: the report queued at once (the caller enters `next` with no
 * await after this), then kept and sent.
 */
export function receiptsAdmitted($: EngineInterface, carried: Carried) {
  if (admitCarried(carried)) {
    void keep(state.holder.engine ?? $)
    void pumpReports()
  }
}

/** A request the gate's `stop` ended: its receipts wait, kept, for their release in this launch. */
export function receiptsStopped($: EngineInterface, carried: Carried) {
  if (stopCarried(carried)) {
    void keep(state.holder.engine ?? $)
    void releaseStopped()
  }
}

/**
 * The reports the child has not acknowledged, sent one after another on its
 * route, each until the child answers it recorded (or moot): one with no
 * answer, or one the child could not record, is tried again after
 * HOLDER_RETRY_MS; a new child takes them up at its ready. On the child's
 * own route, never behind the stream's posts.
 */
async function pumpReports(): Promise<void> {
  const h = state.holder
  const r = h.receipts
  if (r.isPumping) {
    return
  }
  r.isPumping = true
  try {
    for (;;) {
      const report = r.reports[0]
      const relay = h.relay
      const $ = h.engine
      if (report === undefined || relay === undefined || !isCurrent(relay) || $ === undefined || h !== state.holder) {
        return
      }
      // A release goes only while no fence holds (checked at each replay):
      // under a newer one it waits among the stopped again.
      if (report.kind === 'release' && h.fences.size > 0) {
        holdReleases()
        void keep($)
        continue
      }
      // A release is one attempt per fence check: its retry is this loop's,
      // which checks the fences again first.
      const got = await post($, relay, report.kind === 'admit' ? { kind: 'admit', session: report.session, ids: report.ids } : { kind: 'release', session: report.session, items: report.items }, report.kind === 'release' ? 1 : POST_TRIES)
      if (h !== state.holder) {
        return
      }
      if (reportAnswered(report, got) === 'retry') {
        void keep($)
        if (!r.isRetryArmed) {
          r.isRetryArmed = true
          $.clock.after(HOLDER_RETRY_MS, () => {
            r.isRetryArmed = false
            void pumpReports()
          })
        }
        return
      }
      if (r.reports[0] === report) {
        r.reports.shift()
      }
      void keep($)
    }
  } finally {
    r.isPumping = false
  }
}

/**
 * The stopped receipts, released for their retry in this launch once no
 * fence holds: the one that stopped them disarmed or run out, and no newer
 * or renewed one standing. A welcome changes no fence, so it releases
 * nothing. Each says whether its row is still in the live conversation.
 */
async function releaseStopped(): Promise<void> {
  const h = state.holder
  const r = h.receipts
  const $ = h.engine
  if (r.isReleasing || r.stopped.length === 0 || h.fences.size > 0 || !h.isLoaded || $ === undefined) {
    return
  }
  r.isReleasing = true
  try {
    const live = await liveMarks($)
    // A hold that came while the conversation was read keeps them pending.
    if (h !== state.holder || h.fences.size > 0 || r.stopped.length === 0) {
      return
    }
    log(`${r.stopped.length} stopped receipt(s) released for a retry in this launch: no fence holds`)
    releaseStoppedNow(live)
    void keep($)
    void pumpReports()
  } finally {
    r.isReleasing = false
  }
}

// -- origins

/** Whether a main turn runs, or may (a module loaded while one ran). */
const isMainRunning = () => state.mainTurn !== undefined || state.isTurnUnknown

function remember(p: PromptSeen) {
  const h = state.holder
  h.prompts.push(p)
  if (h.prompts.length > PROMPTS_KEPT) {
    h.prompts.shift()
  }
  correlate()
}

/**
 * A prompt submitted to the main loop, by its engine-stamped origin kind,
 * seen at `prompt.submit` before it enters. One the engine names a running
 * turn for (`turnId`) is delivered into that turn: it starts none and says
 * nothing of how that turn started. Any other may start a later turn of its
 * text, never one already running.
 */
export function promptSubmitted(kind: string, text: string, turnId: string | undefined): PromptSeen {
  const p: PromptSeen = { kind, text, seq: ++state.holder.seq, isTaken: turnId !== undefined }
  remember(p)
  return p
}

/**
 * A prompt's row in the main conversation, by its stamp: the same prompt as
 * one submitted with its kind and text and no row yet; one whose stamp names
 * no turn origin is the submission of its text whatever that submission's
 * kind (2.1.316 stamps the row of an `sdk` or a `scheduled-trigger` prompt
 * `unclassified`, measured live); else seen here alone, which while a main
 * turn runs is that turn's (a delivery into it, or the prompt it started
 * with, which identical text cannot tell apart), and evidence for no turn.
 */
export function promptRow(kind: string, text: string, uuid: string) {
  const h = state.holder
  if (h.prompts.some((p) => p.uuid === uuid)) {
    return
  }
  const isUnmatched = (p: PromptSeen) => p.uuid === undefined && p.text === text
  const submitted = h.prompts.findLast((p) => isUnmatched(p) && p.kind === kind) ?? (Object.hasOwn(ORIGINS, kind) ? undefined : h.prompts.findLast(isUnmatched))
  if (submitted !== undefined) {
    submitted.uuid = uuid
    return
  }
  remember({ kind, text, uuid, seq: ++h.seq, isTaken: isMainRunning() })
}

/** A submission settled: one dropped started nothing; one that entered as other text is matched by that text. */
export function promptSettled(p: PromptSeen, entered: { drop?: unknown; text?: unknown }) {
  const h = state.holder
  if (entered.drop !== undefined) {
    const at = h.prompts.indexOf(p)
    if (at !== -1 && !p.isTaken) {
      h.prompts.splice(at, 1)
    }
  } else if (typeof entered.text === 'string' && entered.text !== p.text) {
    p.text = entered.text
    correlate()
  }
}

export function mainTurnStarted(turnId: string, text: string) {
  const h = state.holder
  h.turns.set(turnId, { text, seq: ++h.seq })
  if (h.turns.size > TURNS_KEPT) {
    h.turns.delete(h.turns.keys().next().value!)
  }
  correlate()
}

export function mainTurnOver(turnId: string) {
  state.holder.turns.delete(turnId)
}

/**
 * Each main turn with no origin yet takes the oldest prompt of its text seen
 * before it started and taken by no turn. Prompts of its text that disagree
 * on the origin establish none: the turn is `unknown` and takes them all. A
 * turn's origin, once found, never changes.
 */
function correlate() {
  const h = state.holder
  for (const t of h.turns.values()) {
    if (t.origin !== undefined || t.text === '') {
      continue
    }
    const candidates = h.prompts.filter((p) => !p.isTaken && p.seq < t.seq && p.text === t.text)
    const origins = new Set(candidates.map((p) => ORIGINS[p.kind] ?? 'unknown'))
    if (origins.size === 1) {
      candidates[0]!.isTaken = true
      t.origin = [...origins][0]
    } else if (origins.size > 1) {
      for (const p of candidates) {
        p.isTaken = true
      }
      t.origin = 'unknown'
      log(`prompts of a turn's text disagree on its origin (${[...origins].join(', ')}): unknown`)
    }
  }
}

/** A main turn's origin as the gate's `turn` names it: `unknown` for one no prompt correlates with, or none known. */
export function originOf(turnId: string | undefined): TurnOrigin {
  return (turnId !== undefined ? state.holder.turns.get(turnId)?.origin : undefined) ?? 'unknown'
}
