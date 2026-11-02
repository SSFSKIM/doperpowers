import { describe, expect, test, tier } from 'claude-code/testing'

import { HOLDER_MARGIN_MS, HOLDER_RETRY_MS } from '../../hooks/mods/bridge-holder'
import { SID, harness, hello, line } from './bridge-harness'

tier('user')

/**
 * The receipts of a lane B observer's process (O12 M4b), at the mod: which
 * receipts an admitted model request carried, the reports of them to the
 * child's route (kept and replayed until it records them), the stopped
 * ones' release in the same launch, the activation the child's ready asks
 * for, and the M4a observer's upgrade. The child's side (its activation
 * before the hello, the durable records) is test_holder_receipts.py's; the
 * deliverers', test_holder_deliveries.py's.
 */

const MARKED = { MAWS_LANE: 'B', SMNS_MEMBER: '4242', MAWS_HOLDER_SOCKET: '/tmp/maws/gate.sock' }
const ROUTE = '/tmp/s/bridge/h99.sock'
const GEN = '0123456789abcdef'
const G2 = 'fedcba9876543210'
const E1 = `${GEN}.1`
const LEASE = 400
const FALLBACK = LEASE + HOLDER_MARGIN_MS
const NEW = '6c000002-0000-4000-8000-00000000006c'

const A = 'aaaaaaaaaaaaaaaaaaaaaaaa.0123456789abcdef'
const B = 'bbbbbbbbbbbbbbbbbbbbbbbb.0123456789abcdef'
const C = 'cccccccccccccccccccccccc.0123456789abcdef'

/** A delivery's text as push_live writes it: its receipt's marker first, inside the peer envelope. */
const delivered = (id: string, attempt = 1, said = 'hello there') =>
  `<cross-session-message from-name="peer">\n[sminos receipt ${id} attempt ${attempt}]\n[sminos chat proj SK/peer:1 from peer → @you]\n${said}\n</cross-session-message>`

const bootstrap = (generation = GEN, socket = ROUTE, childPid = 99) => line({ op: 'holder', bootstrap: { socket, nonce: `n-${generation}`, generation, pid: 7, childPid } })
const relayed = (epoch: string, frame: Record<string, unknown>, arm?: number) => line({ op: 'holder', epoch, ...(arm !== undefined && { arm }), frame })
const helloMatch = (session = SID) => line({ op: 'hello', session, pid: 7, socket: `/tmp/s/bridge/${session}.sock`, protocol: 1, nonce: 'n0', lane: 'match' })

type H = ReturnType<typeof harness>

async function flush(h: H) {
  for (let i = 0; i < 8; i++) {
    await h.settle()
  }
}

/** The live conversation as the requests read it: these user texts. */
const live = (h: H, ...texts: string[]) => h.setApiConversation(texts.map((text) => ({ role: 'user', content: [{ type: 'text', text }] })))

/** A marked session whose child's gate was welcomed on E1. */
async function observing(extra: Parameters<typeof harness>[0] = {}) {
  const h = harness({ env: MARKED, messages: [], ...extra })
  await h.start()
  h.children[0]!.write(bootstrap())
  await flush(h)
  h.children[0]!.write(helloMatch())
  h.children[0]!.write(relayed(E1, { t: 'welcome', protocol: 1 }))
  await flush(h)
  return h
}

/** A peer's delivery entering the main conversation as a row (`prompt`, or `delivery` into a running turn). */
const peerRow = (h: H, text: string, door = 'prompt') => h.append(door, { type: 'user', role: 'user', content: [{ type: 'text', text }] }, { origin: { kind: 'peer' } })

/** A main-loop request begun and left running; `hold` keeps it inside its model request once made. */
function request(h: H, turnId: string, index = 0, hold?: Promise<void>) {
  const made = h.requests.length
  const done = h.step({ turnId, index, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'answer' }], hold === undefined ? undefined : () => hold)
  return { done, isMade: () => h.requests.length > made }
}

async function arm(h: H, n: number, fence: number, leaseMs = LEASE) {
  h.children[0]!.write(relayed(E1, { t: 'arm', fence, leaseMs }, n))
  await flush(h)
}

async function answer(h: H, frame: Record<string, unknown>) {
  h.children[0]!.write(relayed(E1, frame))
  await flush(h)
}

function deferred() {
  let release: () => void = () => undefined
  const p = new Promise<void>((resolve) => (release = resolve))
  return { p, release }
}

const admits = (h: H) => h.holderBodies('admit').map((b) => ({ session: b.session, ids: b.ids }))
const releases = (h: H) => h.holderBodies('release').map((b) => ({ session: b.session, items: b.items }))
const keptReceipts = (h: H) => (h.sessionState.get('holder') as { receipts?: unknown } | undefined)?.receipts

describe('receipts: what an admitted request carried (O12 M4b)', () => {
  test("a peer's turn: its row in before the turn began is reported at the turn's first admitted request, once, and the turn names it to the gate", async () => {
    const h = await observing()
    await peerRow(h, delivered(A))
    live(h, delivered(A))
    await h.turn('t1', undefined, delivered(A))
    await arm(h, 1, 1)
    expect(h.holderBodies('turn')).toEqual([expect.objectContaining({ kind: 'turn', epoch: E1, fence: 1, delivery: A })])
    const r = request(h, 't1')
    await flush(h)
    expect(r.isMade()).toBe(false)
    expect(admits(h)).toEqual([])
    await answer(h, { t: 'proceed', fence: 1 })
    expect(r.isMade()).toBe(true)
    await r.done
    expect(admits(h)).toEqual([{ session: SID, ids: [A] }])
    // Acknowledged: a later request carries it again and reports nothing.
    await answer(h, { t: 'disarm', fence: 1 })
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [] })
    await request(h, 't1', 1).done
    expect(admits(h)).toHaveLength(1)
  })

  test("the turn's own prompt row appended after its start is in its first request: the turn's text names it", async () => {
    const h = await observing()
    await h.turn('t1', undefined, delivered(A))
    await peerRow(h, delivered(A))
    live(h, delivered(A))
    await request(h, 't1').done
    expect(admits(h)).toEqual([{ session: SID, ids: [A] }])
  })

  test('several receipts in one request are each reported, in one report to the child', async () => {
    const h = await observing()
    await peerRow(h, delivered(A))
    await peerRow(h, delivered(B))
    live(h, delivered(A), delivered(B))
    await h.turn('t1', undefined, `${delivered(A)}\n${delivered(B)}`)
    await request(h, 't1').done
    expect(admits(h)).toEqual([{ session: SID, ids: [A, B] }])
  })

  test('a row appended during an already-running first step is not that request\'s: the next request reports it', async () => {
    const h = await observing()
    await h.submit('check the deploys', 'composer')
    await h.turn('t1', undefined, 'check the deploys')
    const hold = deferred()
    const first = request(h, 't1', 0, hold.p)
    await flush(h)
    expect(first.isMade()).toBe(true)
    await peerRow(h, delivered(A), 'delivery')
    live(h, 'check the deploys', delivered(A))
    hold.release()
    await first.done
    expect(admits(h)).toEqual([])
    await request(h, 't1', 1).done
    expect(admits(h)).toEqual([{ session: SID, ids: [A] }])
  })

  test('no unseen row settles because another entered next: a row in after the turn began waits for a later request', async () => {
    const h = await observing()
    await peerRow(h, delivered(A))
    await h.turn('t1', undefined, delivered(A))
    // B goes in after the turn began and before its first request.
    await peerRow(h, delivered(B), 'delivery')
    live(h, delivered(A), delivered(B))
    await request(h, 't1').done
    expect(admits(h)).toEqual([{ session: SID, ids: [A] }])
    await request(h, 't1', 1).done
    expect(admits(h)).toEqual([
      { session: SID, ids: [A] },
      { session: SID, ids: [B] },
    ])
  })

  test('a row the live conversation does not hold (a rewind took it out) is in no request; a refused row is none either', async () => {
    const h = await observing()
    await peerRow(h, delivered(A))
    await h.append('prompt', { type: 'user', role: 'user', content: [{ type: 'text', text: delivered(B) }] }, { origin: { kind: 'peer' }, next: async () => ({ deny: 'a hook beneath refused it' }) })
    live(h, delivered(B))
    await h.turn('t1', undefined, 'go')
    await request(h, 't1').done
    expect(admits(h)).toEqual([])
  })

  test('an unmarked session reads nothing of receipts', async () => {
    const h = harness({ messages: [] })
    await h.ready()
    await peerRow(h, delivered(A))
    live(h, delivered(A))
    await h.turn('t1', undefined, delivered(A))
    const reads = h.apiReads()
    await request(h, 't1').done
    expect(h.apiReads()).toBe(reads)
    expect(admits(h)).toEqual([])
  })

  test('the conversation is read only for a request that may carry an unreported receipt', async () => {
    const h = await observing()
    await h.turn('t1', undefined, 'go')
    const reads = h.apiReads()
    await request(h, 't1').done
    await request(h, 't1', 1).done
    expect(h.apiReads()).toBe(reads)
  })
})

describe('receipts: a stopped request (O12 M4b)', () => {
  async function stopped(extra: Parameters<typeof harness>[0] = {}) {
    const h = await observing(extra)
    await peerRow(h, delivered(A, 2))
    live(h, delivered(A, 2))
    await h.turn('t1', undefined, delivered(A, 2))
    await arm(h, 1, 1)
    const r = request(h, 't1')
    await flush(h)
    await answer(h, { t: 'stop', fence: 1, reason: 'reaped' })
    await r.done
    expect(r.isMade()).toBe(false)
    return h
  }

  test('a stop reports nothing; the stopped receipt is kept for its release', async () => {
    const h = await stopped()
    expect(admits(h)).toEqual([])
    expect(releases(h)).toEqual([])
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [{ session: SID, id: A, attempt: 2 }] })
  })

  test('the matching disarm releases it for a retry in this launch, its row still in the conversation (a wake)', async () => {
    const h = await stopped()
    await answer(h, { t: 'disarm', fence: 2 })
    expect(releases(h)).toEqual([])
    await answer(h, { t: 'disarm', fence: 1 })
    expect(releases(h)).toEqual([{ session: SID, items: [{ id: A, attempt: 2, present: true }] }])
    await flush(h)
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [] })
  })

  test('a lost disarm: once the lease and margin run out with no answer it is released; a welcome alone releases nothing', async () => {
    const h = await stopped()
    // The connection is replaced: a new welcome, the fence still standing.
    h.children[0]!.write(relayed(`${GEN}.2`, { t: 'welcome', protocol: 1 }))
    await flush(h)
    expect(releases(h)).toEqual([])
    live(h)
    await h.fire(FALLBACK)
    expect(releases(h)).toEqual([{ session: SID, items: [{ id: A, attempt: 2, present: false }] }])
  })

  test('a newer or renewed hold keeps it pending: the first arm\'s timer ends nothing, another fence holds after the disarm', async () => {
    const h = await stopped()
    // A renewal of fence 1: the first arm's timer ends nothing.
    await arm(h, 2, 1, 2 * LEASE)
    const first = h.timers.find((t) => t.kind === 'after' && t.ms === FALLBACK)!
    first.fn()
    await flush(h)
    expect(releases(h)).toEqual([])
    // A newer fence, then fence 1's disarm: the newer one holds it.
    await arm(h, 3, 5)
    await answer(h, { t: 'disarm', fence: 1 })
    expect(releases(h)).toEqual([])
    await answer(h, { t: 'disarm', fence: 5 })
    expect(releases(h)).toEqual([{ session: SID, items: [{ id: A, attempt: 2, present: true }] }])
  })

  test('a later admitted request carrying it settles it instead: no release follows', async () => {
    const h = await stopped()
    await h.complete('t1')
    await answer(h, { t: 'disarm', fence: 1 })
    expect(releases(h)).toHaveLength(1)
    const again = await stopped()
    await again.turn('t2', undefined, 'go on')
    await arm(again, 2, 3)
    const r = request(again, 't2')
    await flush(again)
    // Fence 1 still stands (no disarm came): both let it go.
    await answer(again, { t: 'proceed', fence: 1 })
    await answer(again, { t: 'proceed', fence: 3 })
    await r.done
    expect(admits(again)).toEqual([{ session: SID, ids: [A] }])
    expect(keptReceipts(again)).toMatchObject({ stopped: [] })
    await answer(again, { t: 'disarm', fence: 1 })
    await answer(again, { t: 'disarm', fence: 3 })
    expect(releases(again)).toEqual([])
  })
})

describe('receipts: reports until the child records them (O12 M4b)', () => {
  test('a report with no answer is kept in $.state and replayed until the child acknowledges it, apart from the stream', async () => {
    let fail = true
    const h = await observing({ holderAnswer: (b) => (b.kind === 'admit' && fail ? 'fail' : undefined) })
    await peerRow(h, delivered(A))
    live(h, delivered(A))
    await h.turn('t1', undefined, delivered(A))
    await request(h, 't1').done
    await flush(h)
    expect(keptReceipts(h)).toEqual({ reports: [{ kind: 'admit', session: SID, ids: [A] }], stopped: [] })
    const tried = admits(h).length
    fail = false
    await h.fire(HOLDER_RETRY_MS)
    expect(admits(h).length).toBeGreaterThan(tried)
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [] })
  })

  test("a storage failure is replayed for what was not recorded; the process's refusal (legacy) ends the report", async () => {
    let storage = true
    const h = await observing({
      holderAnswer: (b) =>
        b.kind !== 'admit' ? undefined : storage ? { status: 200, body: { ok: false, code: 'storage', error: 'disk', receipts: { [A]: 'admitted', [B]: 'unavailable' } } } : { status: 200, body: { ok: true, receipts: { [B]: 'admitted' } } },
    })
    await peerRow(h, delivered(A))
    await peerRow(h, delivered(B))
    live(h, delivered(A), delivered(B))
    await h.turn('t1', undefined, 'go')
    await h.complete('t1')
    await h.turn('t2', undefined, 'go')
    await request(h, 't2').done
    expect(admits(h)).toEqual([{ session: SID, ids: [A, B] }])
    storage = false
    await h.fire(HOLDER_RETRY_MS)
    expect(admits(h)).toEqual([
      { session: SID, ids: [A, B] },
      { session: SID, ids: [B] },
    ])
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [] })
    const legacy = await observing({ holderAnswer: (b) => (b.kind === 'admit' ? { status: 200, body: { ok: false, code: 'legacy', error: 'process 7 does not take receipts (legacy)' } } : undefined) })
    await peerRow(legacy, delivered(C))
    live(legacy, delivered(C))
    await legacy.turn('t1', undefined, delivered(C))
    await request(legacy, 't1').done
    await flush(legacy)
    expect(keptReceipts(legacy)).toEqual({ reports: [], stopped: [] })
  })

  test("a child restart: what the old child did not acknowledge is replayed to the new one at its ready", async () => {
    const h = await observing({ holderAnswer: (b) => (b.kind === 'admit' && b.generation === GEN ? 'fail' : undefined) })
    await peerRow(h, delivered(A))
    live(h, delivered(A))
    await h.turn('t1', undefined, delivered(A))
    await request(h, 't1').done
    h.children[0]!.end()
    await flush(h)
    await h.fire(0)
    h.children[1]!.write(bootstrap(G2, '/tmp/s/bridge/h100.sock', 100))
    await flush(h)
    expect(h.holderBodies('admit').at(-1)).toEqual({ kind: 'admit', generation: G2, session: SID, ids: [A] })
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [] })
  })

  test('a reload: the kept report is replayed by the module that loads next, to its child', async () => {
    const kept = new Map<string, unknown>()
    const before = await observing({ sessionState: kept, holderAnswer: (b) => (b.kind === 'admit' ? 'fail' : undefined) })
    await peerRow(before, delivered(A))
    live(before, delivered(A))
    await before.turn('t1', undefined, delivered(A))
    await request(before, 't1').done
    await flush(before)
    expect(keptReceipts(before)).toMatchObject({ reports: [{ kind: 'admit', session: SID, ids: [A] }] })
    const after = harness({ env: MARKED, sessionState: kept, messages: [{ type: 'user' }] })
    await after.start()
    after.children[0]!.write(bootstrap(G2, '/tmp/s/bridge/h100.sock', 100))
    await flush(after)
    // The module before knew receipts: no upgrade; the report goes to the new child.
    expect(after.holderBodies('ready').at(-1)).toEqual(expect.objectContaining({ kind: 'ready', launch: String(kept.get('launch')) }))
    expect(after.holderBodies('admit')).toEqual([{ kind: 'admit', generation: G2, session: SID, ids: [A] }])
    expect(keptReceipts(after)).toEqual({ reports: [], stopped: [] })
  })

  test('a reload with no correlation stays conservative: the first request of a turn it did not see begin reports nothing; a later one rechecks', async () => {
    const kept = new Map<string, unknown>()
    await observing({ sessionState: kept })
    const after = harness({ env: MARKED, sessionState: kept, messages: [{ type: 'user' }] })
    after.setApiConversation([{ role: 'user', content: [{ type: 'text', text: delivered(A) }] }])
    await after.start()
    after.children[0]!.write(bootstrap(G2, '/tmp/s/bridge/h100.sock', 100))
    await flush(after)
    expect(after.holderBodies('ready').at(-1)).toEqual(expect.objectContaining({ retained: [A] }))
    // A turn running when the module loaded: its first request is not joined to anything.
    await request(after, 't0').done
    expect(admits(after)).toEqual([])
    // Its later request was made after the load: what the conversation held then is in it.
    await request(after, 't0', 1).done
    expect(admits(after)).toEqual([{ session: SID, ids: [A] }])
  })
})

describe('receipts: activation and the upgrade (O12 M4b)', () => {
  test("a fresh process asks the child to activate with its launch and the receipts its conversation holds (a resume's retained rows)", async () => {
    const h = harness({ env: MARKED, messages: [{ type: 'user' }] })
    h.setApiConversation([{ role: 'user', content: [{ type: 'text', text: `${delivered(A)}\n${delivered(B, 3)}` }] }])
    await h.start()
    h.children[0]!.write(bootstrap())
    await flush(h)
    expect(h.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, launch: String(h.sessionState.get('launch')), retained: [A, B] }])
  })

  test("an M4a observer's process: the module asks for the upgrade, holds the M4a fence and goes on observing", async () => {
    // What an M4a module kept: observerStarted, a fence, no receipts.
    const kept = new Map<string, unknown>([
      ['launch', 'LaunchLaunchLaunchLaun'],
      ['lane', 'match'],
      ['holder', { shape: 1, owner: 'm4a', observerStarted: true, armGenerations: 1, fences: [{ epoch: E1, fence: 1, armGeneration: 1, leaseMs: LEASE }] }],
    ])
    const h = harness({ env: MARKED, sessionState: kept, messages: [{ type: 'user' }] })
    await h.start()
    h.children[0]!.write(bootstrap(G2, '/tmp/s/bridge/h100.sock', 100))
    await flush(h)
    expect(h.holderBodies('ready')).toEqual([{ kind: 'ready', generation: G2, upgrade: true }])
    expect(h.children[0]!.argv).toContain('--launch=LaunchLaunchLaunchLaun')
    // The fence it kept holds a request; the observer acknowledges a new arm.
    await h.turn('t1')
    const r = request(h, 't1')
    await flush(h)
    expect(r.isMade()).toBe(false)
    h.children[0]!.write(relayed(`${G2}.1`, { t: 'welcome', protocol: 1 }))
    h.children[0]!.write(relayed(`${G2}.1`, { t: 'arm', fence: 1, leaseMs: LEASE }, 1))
    await flush(h)
    expect(h.holderBodies('armed')).toEqual([{ kind: 'armed', generation: G2, epoch: `${G2}.1`, arm: 1, fence: 1 }])
    expect(kept.get('holder')).toMatchObject({ observerStarted: true, receipts: { reports: [], stopped: [] } })
    await h.fire(FALLBACK)
    h.children[0]!.write(relayed(`${G2}.1`, { t: 'disarm', fence: 1 }))
    await flush(h)
    expect(r.isMade()).toBe(true)
    await r.done
  })

  test('a process whose launch a module before this one kept, with no receipts kept, is an upgrade too; one whose module knew receipts is not', async () => {
    const pre = harness({ env: MARKED, sessionState: new Map<string, unknown>([['launch', 'LaunchLaunchLaunchLaun']]), messages: [{ type: 'user' }] })
    await pre.start()
    pre.children[0]!.write(bootstrap())
    await flush(pre)
    expect(pre.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, upgrade: true }])
    const kept = new Map<string, unknown>()
    await observing({ sessionState: kept })
    const after = harness({ env: MARKED, sessionState: kept, messages: [{ type: 'user' }] })
    await after.start()
    after.children[0]!.write(bootstrap(G2))
    await flush(after)
    expect(after.holderBodies('ready')).toEqual([{ kind: 'ready', generation: G2, launch: String(kept.get('launch')), retained: [] }])
  })
})

describe('receipts: a /clear (O12 M4b)', () => {
  test("reports name the session they were made in: replayed after a /clear, never as the new session's; the old conversation's rows are not the new one's", async () => {
    let fail = true
    const h = await observing({ holderAnswer: (b) => (b.kind === 'admit' && fail ? 'fail' : undefined) })
    await peerRow(h, delivered(A))
    live(h, delivered(A))
    await h.turn('t1', undefined, delivered(A))
    await request(h, 't1').done
    await h.complete('t1')
    // B went in after: its turn never came before the /clear.
    await peerRow(h, delivered(B))
    await h.hook('session.end', {})(h.engine, { reason: 'clear', sessionId: SID }, async () => ({}))
    await flush(h)
    h.setSession(NEW)
    h.timers.filter((t) => t.kind === 'after' && !t.cancelled).at(-1)!.fn()
    await flush(h)
    live(h)
    fail = false
    h.children[1]!.write(bootstrap(G2, '/tmp/s/bridge/h101.sock', 101))
    h.children[1]!.write(hello(NEW, `/tmp/s/bridge/${NEW}.sock`))
    await flush(h)
    expect(h.holderBodies('admit').at(-1)).toEqual({ kind: 'admit', generation: G2, session: SID, ids: [A] })
    // The new conversation's first turn carries its own delivery, reported as
    // the new session's; B's row was the old conversation's, in no request.
    await peerRow(h, delivered(C))
    live(h, delivered(C))
    await h.turn('t2', undefined, delivered(C))
    await request(h, 't2').done
    expect(admits(h).at(-1)).toEqual({ session: NEW, ids: [C] })
    expect(admits(h).flatMap((a) => a.ids)).not.toContain(B)
  })
})
