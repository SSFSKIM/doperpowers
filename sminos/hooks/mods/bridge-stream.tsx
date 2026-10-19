import { isEffort, isRecord, loopKey, message, state } from './bridge-state'
import type { BridgeEvent, Override, Refusal, Request, Streaming } from './bridge-state'

/**
 * The stream: the mod's copy of the session's live state, and the poster that
 * takes every event to the child.
 *
 * The mod keeps the session's live state itself (open turns, every message
 * still streaming with its text and last chunk index, the subagents), so
 * whenever the child's copy may be wrong (a post was lost, a new child said
 * hello) the next post opens with a `resync` that replaces it.
 *
 * Every event goes through `emit`, which folds it into that state (`track`)
 * and queues it for the poster. A step's end is held here until every row of
 * its blocks is named (bridge-rows.tsx names them).
 *
 * A hold is a place in the queue the poster does not post past until its
 * `run` resolves; the events it resolves take its place. Rows no hook saw (a
 * compaction's, bridge-rows.tsx) are named through one, so their notices go
 * out ahead of anything later, though their uuids are read from the disk.
 */

export type Hold = BridgeEvent & {
  type: '@hold'
  /**
   * The loop whose rows past `after` it names: its cut when the hold was
   * placed, or the last row an earlier hold placed at the same cut named.
   */
  loop: string
  after: string
  /** The loop's rows named when it was placed, and those every earlier hold of the loop named since. */
  named: Set<string>
  run: () => Promise<BridgeEvent[]>
}
export const isHold = (e: BridgeEvent | undefined): e is Hold => e?.type === '@hold'

/**
 * A tool event while the bridge is not known to be safe: its input or result
 * may hold what a guard outside the bridge restored. The poster posts nothing
 * past it until a `safe` verdict (bridge-place.tsx) posts it whole; an `off`
 * verdict drops the queue, and queues nothing while it stands (`emit`).
 */
const isWithheld = (e: BridgeEvent | undefined) => state.place !== 'safe' && e?.type === 'tool'

const BATCH_MAX = 500
const QUEUE_MAX = 10_000
/** After a post that failed, the next waits this long. */
const RETRY_MS = 500
/** A step's end waits this long at most for the rows of its blocks the engine appends after the request's result. */
export const STEP_END_WAIT_MS = 1_000
/** Refusals held for the child at most (as many as it keeps). */
const REFUSALS_HELD = 100
/** A chunk's block kind: an `input` chunk is a tool call's arguments. */
const BLOCK_KIND: Record<string, string> = { text: 'text', thinking: 'thinking', tool: 'tool', input: 'tool' }

const messageKey = (turnId: unknown, agentId: unknown, step: unknown) => `${String(turnId)}|${String(agentId)}|${String(step)}`

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
      releaseStepEnd(loopKey(e.agentId))
      state.stepBlocks.delete(loopKey(e.agentId))
      // A hold already placed for it keeps its own copy.
      state.named.delete(String(e.agentId))
    }
  } else if (e.type === 'delivered' && e.outcome === 'refused') {
    state.refusals = [...state.refusals, { key: e.key as Refusal['key'], reason: String(e.reason) }].slice(-REFUSALS_HELD)
  }
}

/** The refusals a post the child answered carried, in its own events or a resync's: the child keeps them. */
function acknowledge(batch: BridgeEvent[]) {
  const name = (k: Refusal['key']) => `${k.project ?? ''}|${k.writer}:${k.seq}`
  const carried = new Set(
    batch.flatMap((e) =>
      e.type === 'resync' ? (e.refused as Refusal[]).map((r) => name(r.key)) : e.type === 'delivered' && e.outcome === 'refused' ? [name(e.key as Refusal['key'])] : [],
    ),
  )
  state.refusals = state.refusals.filter((r) => !carried.has(name(r.key)))
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
export const raisedFields = (r: Request) => ({
  request: r.id,
  tool: r.tool,
  input: r.input,
  agentId: r.agentId,
  ...(r.deadline !== undefined && { deadline: r.deadline }),
  ...(r.isAsync && { async: true }),
  ...(r.isTruncated && { truncated: true }),
  ...(r.toolUseId !== undefined && { toolUseId: r.toolUseId }),
})

/** The live state whole, and what the child keeps for this session: what it replaces its own with. */
export function resyncEvent(): BridgeEvent {
  return {
    type: 'resync',
    turns: [...state.turns.values()],
    // Each message also names the blocks a row settled, so a child taking it
    // over ignores their late chunks as this one does.
    streaming: [...state.messages.values()].map((m) => ({ ...shownMessage(m), settled: [...m.settled].sort((a, b) => a - b) })),
    agents: [...state.agents.values()],
    pending: [...state.requests.values()].map((r) => ({ ...raisedFields(r), t: r.t })),
    settled: state.settled.map((s) => ({ ...s })),
    override: state.override ?? null,
    delivered: Object.fromEntries(state.delivered),
    // Refusals whose post may have been lost: the child merges them into what it keeps.
    refused: state.refusals.map((r) => ({ key: { ...r.key }, reason: r.reason })),
    // Each loop's last row notice: every row up to it has been named.
    cut: { main: null, ...Object.fromEntries(state.cut) },
    // What the session started as: a child whose session start was lost (the
    // first post failed, and its recovery is this resync) still knows it.
    ...(state.info !== undefined && { sessionInfo: { session: state.session, ...state.info } }),
    t: Date.now(),
  }
}

/**
 * Forgets the live state: the session after a /clear starts with none, and
 * no delivery to the old id is the new one's. The model chosen stays, as the
 * terminal's own choice of model does across a /clear.
 */
export function forgetLive() {
  state.turns.clear()
  state.messages.clear()
  // Its agents were set aside first (bridge-agents.tsx, forgetAgents).
  state.agents.clear()
  state.submissions = []
  state.deliveredRows = []
  // A steer or delivery whose append settles after the /clear, and a wake
  // still pending, are the old conversation's: none wakes the new one.
  state.steers = []
  state.wakes = []
  state.refusals = []
  state.delivered.clear()
  state.loopTurns.clear()
  state.stepBlocks.clear()
  state.checks = []
  state.decidedChecks = []
  state.records.clear()
  state.askDialogs.clear()
  state.dialogCalls.clear()
  state.cut.clear()
  state.named.clear()
  // A /clear comes between turns: the new session's main loop is idle.
  state.isTurnUnknown = false
  state.asks.clear()
  state.requests.clear()
  state.settled = []
}

/**
 * The first hello's seed: each loop's last row when the child read its
 * transcript, the cut of every loop that pre-dates the module and has had no
 * notice from it yet (a loop noticed already is cut at its notice, and its
 * rows past the seed are each noticed in turn). A loop the module saw from
 * its first row needs none: every row of it is noticed.
 */
export function adoptSeed(seed: unknown) {
  if (!isRecord(seed)) {
    return
  }
  for (const [loop, uuid] of Object.entries(seed)) {
    if (typeof uuid === 'string' && !state.cut.has(loop) && !state.freshLoops.has(loop)) {
      state.cut.set(loop, uuid)
    }
  }
}

/** What the child kept for the session (its hello's `kept`), taken by a module that holds none yet. */
export function adoptKept(kept: unknown) {
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
    for (const [mark, seq] of Object.entries(delivered)) {
      if (Number.isInteger(seq) && (seq as number) > (state.delivered.get(mark) ?? 0)) {
        state.delivered.set(mark, seq as number)
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
  const dropped = events.reduce((n, e) => n + (e.type === 'gap' ? Number(e.dropped) : e.type === 'resync' || isHold(e) ? 0 : 1), 0)
  requeue([{ type: 'gap', dropped, t: Date.now() }, resyncEvent()])
}

/**
 * The queue replaced by `events` (a resync, which covers what was queued):
 * a hold stays, behind them, while its loop's cut is still the row it names
 * past, so its rows are past the cut they carry. Once a later notice moved
 * the cut, the resync's cut covers its rows: it goes.
 */
export function requeue(events: BridgeEvent[]) {
  state.queue = [...events, ...state.queue.filter((e) => isHold(e) && state.cut.get(e.loop) === e.after)]
}

/** Places a hold (Hold) at the queue's end. */
export function hold(h: Hold) {
  if (state.post === undefined || state.isEnding || state.place === 'off') {
    return
  }
  state.queue.push(h)
  pump()
}

export function emit(event: BridgeEvent) {
  // Nothing is kept for a session with no bridge (an internal fork, a start that failed).
  if (state.post === undefined) {
    return
  }
  const stamped = { ...event, t: Date.now() }
  track(stamped)
  // A bridge that is off has no child to post to: the live state it keeps
  // reaches the child a later safe verdict starts, as that child's resync.
  if (state.isEnding || state.place === 'off') {
    return
  }
  state.queue.push(stamped)
  if (state.queue.length > QUEUE_MAX) {
    lose(state.queue)
  }
  pump()
}

/** Wakes the poster, which posts what is queued. */
export function pump() {
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
export async function poster() {
  for (;;) {
    const { post, socket: socketPath, nonce } = state
    if (post === undefined || socketPath === undefined || state.isWaiting || state.queue.length === 0 || isWithheld(state.queue[0])) {
      await new Promise<void>((resolve) => (state.wake = resolve))
      state.wake = undefined
      continue
    }
    const head = state.queue[0]
    if (isHold(head)) {
      const events = await head.run().catch(() => [])
      const at = state.queue.indexOf(head)
      if (at !== -1) {
        state.queue.splice(at, 1, ...events)
      }
      continue
    }
    const held = state.queue.findIndex((e) => isHold(e) || isWithheld(e))
    const batch = state.queue.splice(0, held === -1 ? BATCH_MAX : Math.min(held, BATCH_MAX))
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
    let isFenced = false
    await post(socketPath, nonce, JSON.stringify(batch)).then(
      (res) => {
        // Refused under the nonce of the child this module still holds: the
        // path is served by a child another instance spawned (a reload).
        // Under an older nonce it is only a post that missed a restart.
        if (res.status === 409 && nonce === state.nonce) {
          isFenced = true
        } else if (!res.ok) {
          lost(`status ${res.status}`)
        } else {
          acknowledge(batch)
        }
      },
      (error: unknown) => lost(message(error)),
    )
    state.isPosting = false
    if (isFenced) {
      retire()
      return
    }
    if (failed && state.after !== undefined) {
      state.isWaiting = true
      state.after(RETRY_MS, () => {
        state.isWaiting = false
        pump()
      })
    }
  }
}

/**
 * This module instance no longer owns the session's bridge (a reload's new
 * instance does): it posts nothing more, its heartbeat stops, and its child,
 * if any is left, is stopped and never respawned.
 */
function retire() {
  state.log?.('bridge: the child serves another module instance now; this one stops')
  state.post = undefined
  state.queue = []
  state.heartbeat?.cancel()
  state.heartbeat = undefined
  state.isPosterRunning = false
  stopChild()
}

export function stopChild() {
  state.generation++
  const child = state.child
  state.child = undefined
  state.socket = undefined
  state.nonce = undefined
  // Leaving the stream kills the child.
  void child?.return({ code: null, signal: null })
}

/**
 * A step's end, posted after every block-row of its step (DX4's step-end
 * relies on it): the engine appends a row it withheld (a refusal, a
 * truncated answer) after the request's result, so an end whose blocks are
 * not all named yet is held until they are, STEP_END_WAIT_MS at most, and
 * goes out before anything later of its loop (its next request, its turn's
 * end, the subagent's stop). With the end out, the step's pairing closes.
 */
export function endStep(key: string, end: BridgeEvent) {
  const s = state.stepBlocks.get(key)
  const isThis = s !== undefined && s.turnId === end.turnId && s.step === end.step
  if (!isThis || !s.starts.some((b) => !s.named.has(b.index)) || state.after === undefined) {
    emit(end)
    if (isThis) {
      state.stepBlocks.delete(key)
    }
    return
  }
  s.heldEnd = end
  state.after(STEP_END_WAIT_MS, () => {
    if (s.heldEnd === end) {
      releaseStepEnd(key)
    }
  })
}

/**
 * Posts the loop's held step end, if one is held. Once a step's end is out its
 * pairing is closed: a row of it that comes later is named by `row-seen`.
 */
export function releaseStepEnd(key: string) {
  const s = state.stepBlocks.get(key)
  const end = s?.heldEnd
  if (s !== undefined && end !== undefined) {
    s.heldEnd = undefined
    emit(end)
    state.stepBlocks.delete(key)
  }
}
