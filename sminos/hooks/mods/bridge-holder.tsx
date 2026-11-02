import type { EngineInterface, HookStream, TurnStepChunk, TurnStepInput, TurnStepResult } from 'claude-code'

import type { HolderKept } from '../../types/sminos'

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
 * - A module that loads into the process (a reload) claims the kept state it
 *   read, at that version, before any request can pass, and holds its fences
 *   each for one full lease and margin from then: the time already spent
 *   cannot be read without a wall clock. Until it has restored them every
 *   main request waits.
 * - A turn's origin is the engine's stamp on the prompt that started it,
 *   seen at `prompt.submit` and in its row, matched to the turn by text
 *   among the prompts seen before it started; a prompt delivered into a
 *   running turn is no turn's evidence. `unknown` when nothing matches, or
 *   when prompts of its text disagree. It is diagnostic: every origin is
 *   fenced alike.
 *
 * M4a changes no delivery and no settlement: a peer's message is settled at
 * its inbox handoff as before, and a turn's `turn` carries no `delivery`.
 */

/** The observer's fallback past a lease: one heartbeat, OX10's production margin. */
export const HOLDER_MARGIN_MS = 5_000
/** How long one held wait on the child's route lasts while a request waits at the fence: a call in flight stops the hook's own budget. */
export const HOLDER_WAIT_MS = 5_000
/** How soon what failed for want of the kept state or the child is tried again: restoring the kept state, an acknowledgement. */
export const HOLDER_RETRY_MS = 1_500
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
/** The engine's prompt origins (PromptOrigin) as OX10's turn origins; any other is `unknown`. */
const ORIGINS: Record<string, TurnOrigin> = { sdk: 'query', 'scheduled-trigger': 'cron', 'task-notification': 'task', peer: 'peer', 'peer-send-message': 'peer' }

export const fenceKey = (epoch: string, fence: number) => `${epoch}#${fence}`
const isCount = (v: unknown, least = 0): v is number => typeof v === 'number' && Number.isInteger(v) && v >= least
const isLease = (v: unknown): v is number => isCount(v, 1) && v <= LEASE_MAX_MS
const log = (text: string) => state.log?.(`bridge: holder: ${text}`)

// -- what the process keeps

function isKept(value: unknown): value is HolderKept {
  return (
    isRecord(value) &&
    value.shape === 1 &&
    typeof value.observerStarted === 'boolean' &&
    isCount(value.armGenerations) &&
    Array.isArray(value.fences) &&
    value.fences.every((f) => isRecord(f) && typeof f.epoch === 'string' && isCount(f.fence) && isCount(f.armGeneration) && isLease(f.leaseMs))
  )
}

const snapshot = (h: HolderState): HolderKept => ({
  shape: 1,
  owner: h.owner,
  observerStarted: h.observerStarted,
  armGenerations: h.armGenerations,
  fences: [...h.fences.values()].map((f) => ({ epoch: f.epoch, fence: f.fence, armGeneration: f.armGeneration, leaseMs: f.leaseMs })),
})

/**
 * Writes what this module holds, after every write before it and once the
 * kept state is restored: true once written. A write that finds another
 * module instance's mark (the one a reload loaded) retires this one, which
 * then keeps and acknowledges nothing.
 */
function keep($: EngineInterface): Promise<boolean> {
  const h = state.holder
  const write = h.writes.then(() => h.loaded).then(() => keepNow($, h))
  h.writes = write
  return write
}

async function keepNow($: EngineInterface, h: HolderState): Promise<boolean> {
  try {
    for (let tries = 0; tries < 3 && !h.isRetired && h === state.holder; tries++) {
      const read = await $.state.get(HOLDER)
      if (isRecord(read.value) && read.value.owner !== h.owner) {
        h.isRetired = true
        log('a later module keeps the fences now: this one stops')
        return false
      }
      const written = await $.state.set(HOLDER, snapshot(h), { ifVersion: read.version })
      if (written.isSet) {
        return true
      }
    }
  } catch (error) {
    log(`the fences are not kept: ${message(error)}`)
  }
  return false
}

/**
 * Restores what a module before this one kept (a reload): one try now, then
 * again every HOLDER_RETRY_MS on this `$` until it holds (bridgeStart's,
 * which outlives its hook).
 */
export async function holderLoaded($: EngineInterface): Promise<void> {
  const h = state.holder
  if (!(await restoreHolder($)) && h === state.holder) {
    $.clock.after(HOLDER_RETRY_MS, () => void holderLoaded($))
  }
}

/** Whether the kept state is restored: a request then needs no await for it. */
export const isHolderLoaded = () => state.holder.isLoaded

/**
 * One try at restoring the kept state, or the one being tried: true once it
 * holds, and from then every main request may be admitted on the fences.
 */
export function restoreHolder($: EngineInterface): Promise<boolean> {
  const h = state.holder
  if (h.isLoaded) {
    return Promise.resolve(true)
  }
  h.restoring ??= claimKept($, h).then((isRestored) => {
    h.restoring = undefined
    if (isRestored && !h.isLoaded) {
      h.isLoaded = true
      h.markLoaded()
      if (h === state.holder) {
        wakeStep()
      }
    }
    return isRestored
  })
  return h.restoring
}

/**
 * A session no gate serves (no marker, or one this process controls) has
 * nothing to restore. Else this module claims the very snapshot it read, at
 * its version (`ifVersion`), with its own fences and the kept ones together,
 * and only then holds the kept ones: a module before it that keeps an arm
 * between the read and the claim makes the claim miss, and the next read has
 * that arm. A kept state that cannot be read, or one this module does not
 * read, restores nothing: a fence the host holds an acknowledgement for may
 * be in it, so requests stay closed.
 */
async function claimKept($: EngineInterface, h: HolderState): Promise<boolean> {
  try {
    if ((await $.env.get('MAWS_LANE')) !== 'B' || state.laneVerdict === 'mismatch') {
      return true
    }
    for (let tries = 0; tries < 3 && h === state.holder; tries++) {
      const read = await $.state.get(HOLDER)
      const kept = read.value === undefined ? undefined : isKept(read.value) ? read.value : null
      if (kept === null) {
        return restoreFailed(h, 'the kept state is not one this module reads')
      }
      const own = snapshot(h)
      const adopted = (kept?.fences ?? []).filter((f) => !h.fences.has(fenceKey(f.epoch, f.fence)))
      const claim: HolderKept = {
        ...own,
        observerStarted: own.observerStarted || kept?.observerStarted === true,
        armGenerations: Math.max(own.armGenerations, kept?.armGenerations ?? 0),
        fences: [...own.fences, ...adopted],
      }
      if (!(await $.state.set(HOLDER, claim, { ifVersion: read.version })).isSet) {
        continue
      }
      h.observerStarted ||= claim.observerStarted
      h.armGenerations = Math.max(h.armGenerations, claim.armGenerations)
      for (const f of adopted) {
        install($, f.epoch, f.fence, f.leaseMs)
      }
      if (adopted.length > 0) {
        log(`${adopted.length} fence(s) held again for a whole lease and margin`)
      }
      return true
    }
    return restoreFailed(h, 'the kept state kept changing under the claim')
  } catch (error) {
    return restoreFailed(h, `the kept state is not read: ${message(error)}`)
  }
}

function restoreFailed(h: HolderState, why: string): false {
  if (h.restoreFailure !== why) {
    h.restoreFailure = why
    log(`${why}: main requests stay closed until it is restored`)
  }
  return false
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
  if (h.isRetired) {
    return
  }
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
  // What a module before this one kept is in before anything is written.
  await h.loaded
  h.observerStarted = true
  while (!(await keep($))) {
    if (h.isRetired || !isCurrent(relay)) {
      return
    }
    log(`observerStarted is not kept: the gate waits, tried again in ${HOLDER_RETRY_MS} ms`)
    await new Promise<void>((resolve) => $.clock.after(HOLDER_RETRY_MS, resolve))
  }
  if (!isCurrent(relay)) {
    return
  }
  const ready = await post($, relay, { kind: 'ready' })
  log(ready?.status === 200 ? `ready (child ${relay.childPid ?? '?'}, lane ${String(ready.answer?.lane)})` : `the child did not take ready (${ready?.status ?? 'no answer'})`)
  // A request waiting at the fence holds its wait on this route from now.
  wakeStep()
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
 * child's 409, a new child) or a later module took over.
 */
async function acknowledge($: EngineInterface, h: HolderState, relay: HolderRelay, a: { epoch: string; arm: number; fence: number }, told: Promise<HolderAsked> | undefined) {
  const what = `arm ${a.arm} of ${a.epoch}`
  const isGone = () => h.isRetired || h !== state.holder || !isCurrent(relay)
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
    return h.isRetired ? 'moot' : 'failed'
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
async function post($: EngineInterface, relay: HolderRelay, body: Record<string, unknown>): Promise<{ status: number; answer?: Record<string, unknown> } | undefined> {
  let failure: unknown
  for (let tries = 0; tries < POST_TRIES && isCurrent(relay); tries++) {
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
  const origin = originOf(step?.turnId ?? state.mainTurn)
  const relay = h.relay
  const turn: Promise<HolderAsked> =
    relay === undefined || !epoch.startsWith(`${relay.generation}.`)
      ? Promise.resolve('moot')
      : post($, relay, { kind: 'turn', epoch, fence, origin }).then((r) => (r === undefined ? 'failed' : r.status === 200 ? 'written' : 'moot'))
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
  const step: FencedStep = { turnId, turns: new Map(), answers: new Map() }
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
 * route, the request abandoned, the restore's next try). A wait held on the
 * child's route keeps a call in flight meanwhile, which stops the hook's own
 * budget (a hook's time, `$.clock.sleep` included, runs only while no `$`
 * call is in flight); with no route, the wait spends that budget.
 */
export async function waitAtFence($: EngineInterface, step: FencedStep, signal: AbortSignal | undefined): Promise<void> {
  const h = state.holder
  if (!h.isLoaded && (await restoreHolder($))) {
    return
  }
  for (const f of h.fences.values()) {
    void askTurn($, f.epoch, f.fence)
  }
  const woken = new Promise<void>((resolve) => {
    step.wake = resolve
    signal?.addEventListener('abort', () => resolve(), { once: true })
  })
  const retry = h.isLoaded ? undefined : $.clock.after(HOLDER_RETRY_MS, () => step.wake?.())
  const relay = h.relay
  const held = relay !== undefined && isCurrent(relay) ? post($, relay, { kind: 'wait', ms: HOLDER_WAIT_MS }).then((r) => r?.status === 200) : Promise.resolve(false)
  await Promise.race([woken, held.then((isHeld) => (isHeld ? undefined : woken))])
  retry?.cancel()
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
 * one submitted with its kind and text and no row yet; else seen here
 * alone, which while a main turn runs is that turn's (a delivery into it,
 * or the prompt it started with, which identical text cannot tell apart),
 * and evidence for no turn.
 */
export function promptRow(kind: string, text: string, uuid: string) {
  const h = state.holder
  if (h.prompts.some((p) => p.uuid === uuid)) {
    return
  }
  const submitted = h.prompts.findLast((p) => p.uuid === undefined && p.kind === kind && p.text === text)
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
