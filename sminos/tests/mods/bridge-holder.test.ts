import { describe, expect, test, tier } from 'claude-code/testing'

import { HOLDER_MARGIN_MS, HOLDER_WAIT_MS } from '../../hooks/mods/bridge-holder'
import { OBSERVER_REASON } from '../../hooks/mods/bridge-controls'
import { GATE_FIXTURE } from './gate-fixture'
import { NONCE, SID, SOCK, childArgv, harness, hello, line } from './bridge-harness'

tier('user')

/**
 * The lane B observer's part in MAWS's release fence (O12 M4a), at the mod:
 * the child's private relay is played by the test, as sminos_holder.py's
 * docstring has it (bootstrap, `holder` relay lines, POST /holder); the
 * child's own side of the wire is test_holder.py's.
 */

/** MAWS's marker and its gate's socket on a `claude -p` child of its engine host (Interfaces §C). */
const MARKED = { MAWS_LANE: 'B', SMNS_MEMBER: '4242', MAWS_HOLDER_SOCKET: '/tmp/maws/gate.sock' }
const ROUTE = '/tmp/s/bridge/h99.sock'
const GEN = '0123456789abcdef'
const E1 = `${GEN}.1`
const E2 = `${GEN}.2`
const LEASE = 400
const FALLBACK = LEASE + HOLDER_MARGIN_MS
const REASON = 'The holder ended this session; reopening it continues the conversation.'

const bootstrap = (generation = GEN, socket = ROUTE, childPid = 99) => line({ op: 'holder', bootstrap: { socket, nonce: `n-${generation}`, generation, pid: 7, childPid } })
const relayed = (epoch: string, frame: Record<string, unknown>, arm?: number) => line({ op: 'holder', epoch, ...(arm !== undefined && { arm }), frame })
const armFrame = (fence: number, leaseMs = LEASE) => ({ t: 'arm', fence, leaseMs })
const helloMatch = line({ op: 'hello', session: SID, pid: 7, socket: SOCK, protocol: 1, nonce: NONCE, lane: 'match' })

type H = ReturnType<typeof harness>

function deferred() {
  let release: () => void = () => undefined
  const p = new Promise<void>((resolve) => (release = resolve))
  return { p, release }
}

/** Lets every chained write and post settle. */
async function flush(h: H) {
  for (let i = 0; i < 6; i++) {
    await h.settle()
  }
}

/** A marked session whose child's gate was welcomed on E1. */
async function observing(extra: Parameters<typeof harness>[0] = {}) {
  const h = harness({ env: MARKED, messages: [], ...extra })
  await h.start()
  h.children[0]!.write(bootstrap())
  await flush(h)
  h.children[0]!.write(helloMatch)
  h.children[0]!.write(relayed(E1, { t: 'welcome', protocol: 1 }))
  await flush(h)
  return h
}

/** The frames the mod asked the child to write on the gate, in the order asked. */
const toGate = (h: H) =>
  h.holderBodies('armed', 'turn').map((b) =>
    b.kind === 'armed' ? { t: 'armed', epoch: b.epoch, arm: b.arm, fence: b.fence } : { t: 'turn', epoch: b.epoch, fence: b.fence, origin: b.origin, ...('delivery' in b && { delivery: b.delivery }) },
  )

/** A main-loop (or a subagent's) request begun and left running; `hold` keeps it inside its model request once made. */
function request(h: H, turnId: string, index = 0, agentId?: string, hold?: Promise<void>) {
  const made = h.requests.length
  const done = h.step({ turnId, index, model: 'm', messageCount: 1, ...(agentId !== undefined && { agentId }) }, [{ kind: 'text', index: 0, text: 'answer' }], hold === undefined ? undefined : () => hold)
  return { done, isMade: () => h.requests.length > made, made: () => h.requests.length - made }
}

async function arm(h: H, epoch: string, n: number, fence: number, leaseMs = LEASE, child = 0) {
  h.children[child]!.write(relayed(epoch, armFrame(fence, leaseMs), n))
  await flush(h)
}

async function answer(h: H, epoch: string, frame: Record<string, unknown>, child = 0) {
  h.children[child]!.write(relayed(epoch, frame))
  await flush(h)
}

describe('lane B: the observer and its relay (O12 M4a)', () => {
  test("the child's bootstrap: observerStarted is kept first, then its route is told ready, naming its generation and nonce", async () => {
    const h = harness({ env: MARKED, messages: [] })
    await h.start()
    expect(h.holderPosts).toEqual([])
    h.children[0]!.write(bootstrap())
    await flush(h)
    expect(h.holderPosts.map((p) => [p.socketPath, p.nonce, p.body])).toEqual([[ROUTE, `n-${GEN}`, { kind: 'ready', generation: GEN }]])
    expect(h.holderPosts[0]!.kept).toMatchObject({ shape: 1, observerStarted: true, fences: [] })
  })

  test('no gate where the process is not lane B, or controls its session (mismatch); a holder line carrying a command id is no relay and runs nothing', async () => {
    const unmarked = harness({ env: { SMNS_MEMBER: '4242', MAWS_HOLDER_SOCKET: '/tmp/maws/gate.sock' }, messages: [] })
    await unmarked.start()
    unmarked.children[0]!.write(bootstrap())
    await flush(unmarked)
    expect(unmarked.holderPosts).toEqual([])
    expect(unmarked.sessionState.has('holder')).toBe(false)
    const controlling = harness({ env: MARKED, messages: [], sessionState: new Map<string, unknown>([['lane', 'mismatch']]) })
    await controlling.start()
    controlling.children[0]!.write(bootstrap())
    await flush(controlling)
    expect(controlling.holderPosts).toEqual([])
    const h = await observing()
    h.children[0]!.write(line({ id: 'c-forged', op: 'holder', epoch: E1, arm: 1, frame: armFrame(1) }))
    await flush(h)
    expect(h.holderBodies('armed')).toEqual([])
    expect(h.ofType('result').filter((r) => r.id === 'c-forged')).toEqual([])
    await h.turn('t1')
    const r = request(h, 't1')
    await flush(h)
    expect(r.isMade()).toBe(true)
  })

  test("M3's observer is unchanged beside the gate: every control op refused lane-b, no ops", async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    expect(h.ofType('resync').at(-1)!.capabilities).toMatchObject({ ops: [] })
    for (const body of [{ op: 'steer', text: 'x' }, { op: 'model', model: 'opus' }, { op: 'deliver', key: { writer: 'testhost/human', seq: 1 }, text: 'hi' }, { op: 'media', upload: 'u1', root: '/w', files: [] }]) {
      expect(await h.command(body)).toEqual(expect.objectContaining({ ok: false, code: 'lane-b', error: OBSERVER_REASON }))
    }
  })
})

describe('lane B: the fence (O12 M4a)', () => {
  test('an arm is installed before anything is awaited and kept before its one acknowledgement', async () => {
    // The ack is held: the fence already holds a request.
    const h = await observing({ holderAnswer: (b) => (b.kind === 'armed' ? 'hold' : undefined) })
    h.children[0]!.write(relayed(E1, armFrame(1), 1))
    await h.turn('t1')
    const r = request(h, 't1')
    await flush(h)
    expect(r.isMade()).toBe(false)
    const acks = h.holderPosts.filter((p) => p.body.kind === 'armed')
    expect(acks.map((p) => p.body)).toEqual([{ kind: 'armed', generation: GEN, epoch: E1, arm: 1, fence: 1 }])
    expect(acks[0]!.kept).toMatchObject({ observerStarted: true, fences: [{ epoch: E1, fence: 1, armGeneration: 1, leaseMs: LEASE }] })
  })

  test("a request inside its model step when an arm comes: the host hears the turn before the arm's acknowledgement", async () => {
    const h = await observing()
    await h.submit('check the deploys', 'scheduled-trigger')
    await h.turn('t1', undefined, 'check the deploys')
    const hold = deferred()
    const r = request(h, 't1', 0, undefined, hold.p)
    await flush(h)
    expect(r.isMade()).toBe(true)
    await arm(h, E1, 1, 7)
    expect(toGate(h)).toEqual([
      { t: 'turn', epoch: E1, fence: 7, origin: 'cron' },
      { t: 'armed', epoch: E1, arm: 1, fence: 7 },
    ])
    hold.release()
    await r.done
    expect(r.made()).toBe(1)
  })

  test('a main turn between its requests (a tool running) is told too; a subagent alone never stands for the main loop', async () => {
    const h = await observing()
    await h.turn('t1')
    await arm(h, E1, 1, 1)
    expect(toGate(h)).toEqual([
      { t: 'turn', epoch: E1, fence: 1, origin: 'unknown' },
      { t: 'armed', epoch: E1, arm: 1, fence: 1 },
    ])
    const s = await observing()
    await s.turn('ta', 'a1')
    const hold = deferred()
    const sub = request(s, 'ta', 0, 'a1', hold.p)
    await flush(s)
    await arm(s, E1, 1, 1)
    expect(toGate(s)).toEqual([{ t: 'armed', epoch: E1, arm: 1, fence: 1 }])
    // And with the fence armed, a subagent's request neither waits nor asks.
    const sub2 = request(s, 'ta', 1, 'a1')
    await flush(s)
    expect(sub2.isMade()).toBe(true)
    expect(s.holderBodies('turn')).toEqual([])
    hold.release()
    await sub.done
  })

  test('renewals of one fence: each acknowledged once, in the order they came, never two in one, a later one never ahead of an earlier one', async () => {
    let held: ((status: number, body?: unknown) => void) | undefined
    const h = await observing({ holderAnswer: (b) => (b.kind === 'armed' && b.arm === 1 ? 'hold' : undefined) })
    h.children[0]!.write(relayed(E1, armFrame(1), 1))
    h.children[0]!.write(relayed(E1, armFrame(1), 2))
    h.children[0]!.write(relayed(E1, armFrame(1), 3))
    await flush(h)
    expect(h.holderBodies('armed').map((b) => b.arm)).toEqual([1])
    held = h.holderPosts.find((p) => p.body.kind === 'armed')!.answer
    held(200, { ok: true, sent: 1, waiting: 0 })
    await flush(h)
    expect(toGate(h)).toEqual([1, 2, 3].map((n) => ({ t: 'armed', epoch: E1, arm: n, fence: 1 })))
  })

  test('a renewal while a request waits on its fence: its acknowledgement follows the turn already asked, with no second turn', async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    await h.turn('t1')
    const r = request(h, 't1')
    await flush(h)
    await arm(h, E1, 2, 1)
    expect(toGate(h)).toEqual([
      { t: 'armed', epoch: E1, arm: 1, fence: 1 },
      { t: 'turn', epoch: E1, fence: 1, origin: 'unknown' },
      { t: 'armed', epoch: E1, arm: 2, fence: 1 },
    ])
    expect(r.isMade()).toBe(false)
    await answer(h, E1, { t: 'proceed', fence: 1 })
    await r.done
    expect(r.made()).toBe(1)
  })

  for (const order of [['proceed', 'disarm'], ['disarm', 'proceed']]) {
    test(`a waiting request: ${order.join(' then ')} lets it go, its request made once; the wait keeps a call in flight on the route`, async () => {
      const h = await observing()
      await arm(h, E1, 1, 2)
      await h.turn('t1')
      const r = request(h, 't1')
      await flush(h)
      expect(r.isMade()).toBe(false)
      expect(h.holderBodies('turn')).toEqual([{ kind: 'turn', generation: GEN, epoch: E1, fence: 2, origin: 'unknown' }])
      expect(h.holderBodies('wait').at(-1)).toEqual({ kind: 'wait', generation: GEN, ms: HOLDER_WAIT_MS })
      await answer(h, E1, { t: order[0]!, fence: 2 })
      expect(r.isMade()).toBe(true)
      await answer(h, E1, { t: order[1]!, fence: 2 })
      await r.done
      expect(r.made()).toBe(1)
    })
  }

  test("stop: no model request; the reason streams as the step's one text, then an end_turn stop, and the step's result says so", async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    await h.turn('t1')
    const r = request(h, 't1')
    await flush(h)
    await answer(h, E1, { t: 'stop', fence: 1, reason: REASON })
    const { yielded, returned } = await r.done
    expect(r.made()).toBe(0)
    expect(yielded).toEqual([
      { kind: 'text', index: 0, text: REASON },
      { kind: 'stop', stopReason: 'end_turn', usage: null },
    ])
    expect(returned).toEqual({ turnId: 't1', index: 0, answer: REASON, toolUses: [], stopReason: 'end_turn', usage: null })
    // The session's stream shows it as the step's output.
    expect(h.ofType('chunk').map((c) => c.chunk)).toEqual(yielded)
    // A stop outlives a later disarm of its fence: the next request asks again.
    await answer(h, E1, { t: 'disarm', fence: 1 })
    const next = request(h, 't1', 1)
    await flush(h)
    expect(next.isMade()).toBe(true)
  })

  test("the accepted gap: a peer's turn stopped says `peer` with no delivery, and nothing settles or keeps a receipt (M4b's)", async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    await h.submit('[sminos chat p from peer] hello', 'peer')
    await h.turn('t1', undefined, '[sminos chat p from peer] hello')
    const r = request(h, 't1')
    await flush(h)
    await answer(h, E1, { t: 'stop', fence: 1, reason: REASON })
    await r.done
    expect(h.holderBodies('turn')).toEqual([{ kind: 'turn', generation: GEN, epoch: E1, fence: 1, origin: 'peer' }])
    expect(h.events().filter((e) => e.type === 'delivered' || e.type === 'receipt')).toEqual([])
    expect([...h.sessionState.keys()].sort()).toEqual(['holder', 'launch', 'lane'].sort())
  })

  test('no answer: the request goes once the latest lease and the margin pass by the relative timer, never by the wall clock; an earlier arm\'s timer ends nothing', async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    await arm(h, E1, 2, 1)
    await h.turn('t1')
    const r = request(h, 't1')
    await flush(h)
    // The wall clock jumps an hour forward, then two back: nothing moves.
    h.advance(3_600_000)
    await h.fire(30_000)
    h.advance(-7_200_000)
    await flush(h)
    expect(r.isMade()).toBe(false)
    const timers = h.timers.filter((t) => t.kind === 'after' && t.ms === FALLBACK)
    expect(timers.map((t) => t.cancelled)).toEqual([true, false])
    // The first arm's timer, had it run: the renewal stands.
    timers[0]!.fn()
    await flush(h)
    expect(r.isMade()).toBe(false)
    await h.fire(FALLBACK)
    expect(r.isMade()).toBe(true)
    await r.done
    expect(h.sessionState.get('holder')).toMatchObject({ fences: [] })
  })

  test('epochs: fence 1 reused on a new connection is another fence; a new epoch\'s proceed and a reply naming no fence release nothing of the old one', async () => {
    const h = await observing({ holderAnswer: (b) => (b.kind === 'turn' && b.epoch === E1 ? { status: 409, body: { ok: false, code: 'epoch' } } : undefined) })
    await arm(h, E1, 1, 1)
    // The host was replaced: E1 is over (its socket gone), E2 welcomed.
    await answer(h, E2, { t: 'welcome', protocol: 1 })
    await arm(h, E2, 1, 1, 2 * LEASE)
    expect(h.sessionState.get('holder')).toMatchObject({ fences: [{ epoch: E1, fence: 1 }, { epoch: E2, fence: 1 }] })
    await h.turn('t1')
    const r = request(h, 't1')
    await flush(h)
    expect(h.holderBodies('turn').map((b) => b.epoch)).toEqual([E1, E2])
    await answer(h, E2, { t: 'proceed', fence: 1 })
    await answer(h, E2, { t: 'proceed', fence: 9 })
    await answer(h, E1, { t: 'disarm', fence: 2 })
    expect(r.isMade()).toBe(false)
    // E1's fence runs out by its own lease: then every epoch has let it go.
    await h.fire(FALLBACK)
    expect(r.isMade()).toBe(true)
    await r.done
  })

  test('a child restart replaces the relay, not the holds: the new child is told ready, an old epoch\'s fence holds until its own timer, a line naming it from the new child releases nothing', async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    h.children[0]!.end()
    await flush(h)
    await h.fire(0)
    expect(h.children[1]!.argv).toEqual([...childArgv(h), '--lane', 'match'])
    const G2 = 'fedcba9876543210'
    h.children[1]!.write(bootstrap(G2, '/tmp/s/bridge/h100.sock', 100))
    await flush(h)
    expect(h.holderBodies('ready').at(-1)).toEqual({ kind: 'ready', generation: G2 })
    expect(h.holderPosts.at(-1)!.kept).toMatchObject({ observerStarted: true, fences: [{ epoch: E1, fence: 1 }] })
    await h.turn('t1')
    const r = request(h, 't1')
    await flush(h)
    expect(r.isMade()).toBe(false)
    // No connection is left to ask on for E1; the wait is held on the new route.
    expect(h.holderBodies('turn')).toEqual([])
    expect(h.holderPosts.filter((p) => p.body.kind === 'wait').at(-1)!.socketPath).toBe('/tmp/s/bridge/h100.sock')
    h.children[1]!.write(relayed(E1, { t: 'proceed', fence: 1 }))
    h.children[1]!.write(relayed(E1, { t: 'disarm', fence: 1 }))
    await flush(h)
    expect(r.isMade()).toBe(false)
    await h.fire(FALLBACK)
    expect(r.isMade()).toBe(true)
    await r.done
  })

  test('a /clear: the new session\'s child is started and told ready, and the holds stand', async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    await h.hook('session.end', {})(h.engine, { reason: 'clear', sessionId: SID }, async () => ({}))
    await flush(h)
    const NEW = '6c000002-0000-4000-8000-00000000006c'
    h.setSession(NEW)
    h.timers.filter((t) => t.kind === 'after' && !t.cancelled).at(-1)!.fn()
    await flush(h)
    expect(h.children[0]!.killed).toBe(true)
    expect(h.children[1]!.argv).toEqual([...childArgv(h, NEW), '--lane', 'match'])
    const G2 = 'fedcba9876543210'
    h.children[1]!.write(bootstrap(G2, '/tmp/s/bridge/h101.sock', 101))
    h.children[1]!.write(hello(NEW, `/tmp/s/bridge/${NEW}.sock`))
    await flush(h)
    expect(h.holderBodies('ready').at(-1)).toEqual({ kind: 'ready', generation: G2 })
    await h.turn('t2')
    const r = request(h, 't2')
    await flush(h)
    expect(r.isMade()).toBe(false)
    await h.fire(FALLBACK)
    expect(r.isMade()).toBe(true)
    await r.done
  })

  test('a reload holds the kept fences before any request passes, for one whole lease and margin from the load, and keeps observerStarted', async () => {
    const kept = new Map<string, unknown>()
    const before = await observing({ sessionState: kept })
    await arm(before, E1, 1, 1)
    // The module that loads next, a request before its session start.
    const after = harness({ env: MARKED, sessionState: kept, messages: [{ type: 'user' }] })
    await after.turn('t1')
    const r = request(after, 't1')
    await flush(after)
    expect(r.isMade()).toBe(false)
    expect(after.timers.filter((t) => t.kind === 'after' && t.ms === FALLBACK)).toHaveLength(1)
    expect(kept.get('holder')).toMatchObject({ observerStarted: true, fences: [{ epoch: E1, fence: 1, leaseMs: LEASE }] })
    await after.fire(FALLBACK)
    expect(r.isMade()).toBe(true)
    await r.done
    expect(kept.get('holder')).toMatchObject({ observerStarted: true, fences: [] })
  })

  test('a module a later one replaced (its mark on the kept state another\'s) keeps and acknowledges nothing more', async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    const kept = h.sessionState.get('holder') as Record<string, unknown>
    h.sessionState.set('holder', { ...kept, owner: 'a-later-module' })
    await arm(h, E1, 2, 1)
    expect(h.holderBodies('armed').map((b) => b.arm)).toEqual([1])
    expect(h.sessionState.get('holder')).toMatchObject({ owner: 'a-later-module' })
  })
})

describe('lane B: a main turn\'s origin (O12 M4a)', () => {
  const ORIGINS: [string, string][] = [
    ['sdk', 'query'],
    ['scheduled-trigger', 'cron'],
    ['task-notification', 'task'],
    ['peer', 'peer'],
    ['peer-send-message', 'peer'],
    ['composer', 'unknown'],
  ]
  for (const [kind, origin] of ORIGINS) {
    test(`a turn started by a ${kind} prompt is fenced as ${origin} at every main request, subagents' requests alongside asking nothing`, async () => {
      const h = await observing()
      await arm(h, E1, 1, 1)
      await h.submit(`do the ${kind} thing`, kind)
      await h.turn('t1', undefined, `do the ${kind} thing`)
      for (const index of [0, 1, 2]) {
        // A subagent's request alongside goes at once, asking nothing.
        const sub = request(h, 'ta', index, 'a1')
        await flush(h)
        expect(sub.isMade()).toBe(true)
        await sub.done
        const r = request(h, 't1', index)
        await flush(h)
        expect(r.isMade()).toBe(false)
        await answer(h, E1, { t: 'proceed', fence: 1 })
        await r.done
        expect(r.made()).toBe(1)
      }
      expect(h.holderBodies('turn').map((b) => b.origin)).toEqual([origin, origin, origin])
    })
  }

  test('with nothing to correlate the origin is unknown, and fenced alike; a prompt delivered into the running turn changes nothing of its origin', async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    await h.turn('t1', undefined, 'a turn no prompt was seen for')
    const r = request(h, 't1')
    await flush(h)
    await answer(h, E1, { t: 'proceed', fence: 1 })
    await r.done
    await h.submit('later words', 'peer', { turnId: 't1' })
    const r2 = request(h, 't1', 1)
    await flush(h)
    await answer(h, E1, { t: 'proceed', fence: 1 })
    await r2.done
    expect(h.holderBodies('turn').map((b) => b.origin)).toEqual(['unknown', 'unknown'])
    // A cron turn stays cron when a peer's words arrive in it.
    await h.complete('t1')
    await h.submit('nightly', 'scheduled-trigger')
    await h.turn('t2', undefined, 'nightly')
    await h.submit('a peer meanwhile', 'peer', { turnId: 't2' })
    const r3 = request(h, 't2')
    await flush(h)
    await answer(h, E1, { t: 'proceed', fence: 1 })
    await r3.done
    expect(h.holderBodies('turn').at(-1)!.origin).toBe('cron')
  })

  test('a prompt seen only as its row (session.append, engine-stamped) correlates; the same prompt seen at submit and as its row starts one turn, not two', async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    await h.append('prompt', { type: 'user', role: 'user', content: [{ type: 'text', text: 'a task finished' }] }, { origin: { kind: 'task-notification' } })
    await h.turn('t1', undefined, 'a task finished')
    const r = request(h, 't1')
    await flush(h)
    await answer(h, E1, { t: 'proceed', fence: 1 })
    await r.done
    await h.complete('t1')
    // A cron prompt at submit, then its row; a later query of the same text is a query.
    await h.submit('status', 'scheduled-trigger')
    await h.append('prompt', { type: 'user', role: 'user', content: [{ type: 'text', text: 'status' }] }, { origin: { kind: 'scheduled-trigger' } })
    await h.turn('t2', undefined, 'status')
    await h.complete('t2')
    await h.submit('status', 'sdk')
    await h.turn('t3', undefined, 'status')
    const r3 = request(h, 't3')
    await flush(h)
    await answer(h, E1, { t: 'proceed', fence: 1 })
    await r3.done
    expect(h.holderBodies('turn').map((b) => b.origin)).toEqual(['task', 'query'])
  })

  test('a dropped submission starts nothing: its origin is never taken by a later turn', async () => {
    const h = await observing()
    await arm(h, E1, 1, 1)
    await h.submit('again', 'scheduled-trigger', { entered: { drop: 'not now' } })
    await h.turn('t1', undefined, 'again')
    const r = request(h, 't1')
    await flush(h)
    await answer(h, E1, { t: 'proceed', fence: 1 })
    await r.done
    expect(h.holderBodies('turn').map((b) => b.origin)).toEqual(['unknown'])
  })
})

/**
 * O16's gate fixture (p5-o16-gate.jsonl, MAWS's copied byte for byte;
 * gate-fixture.ts holds it line for line, test_holder.py checking the two
 * agree), each case played at the mod's fence: the host's frames go to the
 * mod as the child relays them, and the frames the mod asks the child to
 * write must be the fixture's observer frames in order. A main request is
 * begun where the fixture's observer sends a `turn`, or before an arm the
 * fixture's observer answered with a `turn` (it was in a main step when the
 * arm came, P4). Allowed beyond the fixture: an `armed` right after a `turn`
 * of its fence (the arm met a running step: turn first, then its ack; P4,
 * R4) and, after the fixture's frames, the `armed` of each arm the fixture's
 * observer left unacknowledged (R4: a late ack is valid). Every relayed arm
 * gets exactly one `armed`, in the order the arms came (R1). `hello` and `hb`
 * are the child's (test_holder.py). A peer `delivery` in the fixture is an
 * opaque input of the relay, which M4a's production turns omit.
 */
describe("O16's gate fixture at the mod's fence (O12 M4a)", () => {
  type Frame = Record<string, unknown> & { t: string }
  type Row = { case: string; from?: 'observer' | 'host'; frame?: Frame; event?: string }
  const rows = GATE_FIXTURE.slice(1).map((l) => JSON.parse(l) as Row)
  const KINDS: Record<string, string> = { query: 'sdk', cron: 'scheduled-trigger', task: 'task-notification', peer: 'peer', unknown: 'composer' }
  const gateFrame = (f: Frame) => (f.t === 'turn' ? { t: 'turn', fence: f.fence, origin: f.origin } : { t: 'armed', fence: f.fence })

  async function play(name: string) {
    const caseRows = rows.filter((r) => r.case === name)
    const h = harness({ env: MARKED, messages: [] })
    await h.start()
    h.children[0]!.write(bootstrap())
    h.children[0]!.write(helloMatch)
    await flush(h)
    const expected: Record<string, unknown>[] = []
    const arms: { epoch: string; arm: number }[] = []
    let epochs = 0
    let epoch = ''
    let armed = 0
    let silenced = false
    let step: (ReturnType<typeof request> & { release: () => void }) | undefined
    const begin = async (origin: unknown) => {
      const text = `${name}: the turn`
      await h.submit(text, KINDS[String(origin)] ?? 'composer')
      await h.turn('t1', undefined, text)
      const hold = deferred()
      step = { ...request(h, 't1', 0, undefined, hold.p), release: hold.release }
      await flush(h)
    }
    for (const [i, row] of caseRows.entries()) {
      if (row.event === 'silence') {
        // The baseline heals by a second hello, which M4a's child never says (R5): played up to here (P3c).
        silenced = true
        break
      }
      if (row.event !== undefined || row.frame === undefined) {
        continue
      }
      const frame = row.frame
      if (row.from === 'observer') {
        if (frame.t === 'armed' || frame.t === 'turn') {
          expected.push(gateFrame(frame))
        }
        if (frame.t === 'turn' && step === undefined) {
          await begin(frame.origin)
        }
        continue
      }
      if (frame.t === 'welcome') {
        epoch = `${GEN}.${++epochs}`
        armed = 0
      }
      if (frame.t === 'arm' && step === undefined) {
        const answeredBy = caseRows.slice(i + 1).find((r) => r.from === 'observer' && (r.frame?.t === 'armed' || r.frame?.t === 'turn'))
        if (answeredBy?.frame?.t === 'turn') {
          await begin(answeredBy.frame.origin)
        }
      }
      const n = frame.t === 'arm' ? ++armed : undefined
      if (n !== undefined) {
        arms.push({ epoch, arm: n })
      }
      h.children[0]!.write(relayed(epoch, frame, n))
      await flush(h)
    }
    step?.release()
    const outcome = await step?.done
    await flush(h)
    return { h, expected, arms, step, outcome, silenced, stopped: caseRows.some((r) => r.frame?.t === 'stop') }
  }

  /** The mod's gate frames against the fixture's observer frames, with the allowances above. */
  function matches(got: Record<string, unknown>[], expected: Record<string, unknown>[]) {
    let g = 0
    for (const want of expected) {
      const prior = got[g - 1]
      if (got[g]?.t === 'armed' && want.t !== 'armed' && prior?.t === 'turn' && prior.fence === got[g]!.fence) {
        g++
      }
      expect({ at: g, frame: got[g] }).toEqual({ at: g, frame: expect.objectContaining(want) })
      g++
    }
    for (; g < got.length; g++) {
      expect({ at: g, late: got[g]!.t }).toEqual({ at: g, late: 'armed' })
    }
  }

  const cases = [...new Set(rows.map((r) => r.case))]
  test('carries the eight cases this replay plays', () => {
    expect(cases).toEqual(['proceed', 'stop', 'armed-renewing-turn-proceed', 'armed-veto-turn-proceed', 'no-answer', 'renew', 'heartbeat-loss', 'server-restart', 'no-row'])
  })

  for (const name of cases) {
    test(`${name}: the mod's frames are the fixture's observer frames, every arm acknowledged once in order`, async () => {
      const { h, expected, arms, step, outcome, stopped } = await play(name)
      const got = toGate(h).map((f) => ({ ...f }))
      matches(got, expected)
      expect(got.filter((f) => f.t === 'turn').every((f) => !('delivery' in f))).toBe(true)
      expect(got.filter((f) => f.t === 'armed').map((f) => ({ epoch: f.epoch, arm: f.arm }))).toEqual(arms)
      if (step !== undefined) {
        // A turn before the signal enters `next` once; one after it stops with no request.
        expect(step.made()).toBe(stopped ? 0 : 1)
        expect(outcome!.returned).toMatchObject({ stopReason: 'end_turn' })
      }
      if (name === 'no-row') {
        expect(h.holderBodies().map((b) => b.kind)).toEqual(['ready'])
      }
    })
  }

  // What only the fix-wave host and its fixture can show (decisions P3): named, never skipped silently.
  test('PENDING P3a: the final SIGTERM\'s confirmed-lease check is the fix-wave host\'s (the joint proof)', () => {
    expect(cases).toContain('stop')
  })
  test('PENDING P3b: the host awaiting `armed` for a renewal while signalled is the fix-wave host\'s; the mod acknowledges every renewal once installed (`renew`, played)', () => {
    expect(cases).toContain('renew')
  })
  test('PENDING P3c: `heartbeat-loss` healed by `hb` on the same connection awaits the fix-wave fixture; played here up to its silence', async () => {
    expect((await play('heartbeat-loss')).silenced).toBe(true)
  })
})
