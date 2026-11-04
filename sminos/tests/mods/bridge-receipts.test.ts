import { describe, expect, test, tier } from 'claude-code/testing'

import { HOLDER_MARGIN_MS, HOLDER_RETRY_MS, STARTUP_WAIT_MS } from '../../hooks/mods/bridge-holder'
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

/** The child's bootstrap; `processAge` its word on claude's process (seconds run, a fresh one by default). */
/** A wake as holder_wake writes it: a pointer to the body above, its marker saying it is a wake. */
const woken = (id: string, attempt: number) => `<cross-session-message from-name="peer">\n[sminos receipt ${id} attempt ${attempt} wake]\n[sminos chat proj SK/peer:1 from peer → @you, again]\nIt is above in this conversation, delivered before: read it there.\n</cross-session-message>`

const bootstrap = (generation = GEN, socket = ROUTE, childPid = 99, processAge: number | null = 1) => line({ op: 'holder', bootstrap: { socket, nonce: `n-${generation}`, generation, pid: 7, childPid, processAge } })
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

  test('a later incarnation never vouches for an older row a rewind took out: a repeated write after the turn began waits for a later request', async () => {
    const h = await observing()
    await peerRow(h, delivered(A))
    // A rewind takes A's row out; a turn starts without it.
    live(h)
    await h.turn('t1', undefined, 'go')
    // The inbox writes A again after the turn began: not in its first request.
    await peerRow(h, delivered(A), 'delivery')
    live(h, 'go', delivered(A))
    await request(h, 't1').done
    expect(admits(h)).toEqual([])
    await request(h, 't1', 1).done
    expect(admits(h)).toEqual([{ session: SID, ids: [A] }])
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

describe('receipts: a wake and its body (O12 M4b)', () => {
  test('a wake is admitted only with its body in the conversation; without it nothing is admitted and the receipt is released for a full retry', async () => {
    const h = await observing()
    // A rewind took the body out before the wake came: the wake alone is in.
    await peerRow(h, woken(A, 2))
    live(h, woken(A, 2))
    await h.turn('t1', undefined, woken(A, 2))
    await request(h, 't1').done
    await flush(h)
    expect(admits(h)).toEqual([])
    expect(releases(h)).toEqual([{ session: SID, items: [{ id: A, attempt: 2, present: false }] }])
    // The full body comes again (attempt 3): admitted.
    await h.complete('t1')
    await peerRow(h, delivered(A, 3))
    live(h, woken(A, 2), delivered(A, 3))
    await h.turn('t2', undefined, delivered(A, 3))
    await request(h, 't2').done
    expect(admits(h)).toEqual([{ session: SID, ids: [A] }])
  })

  test("a full retry that came after a later step entered is not that step's body, though the turn's text names the wake: the next request admits it", async () => {
    const h = await observing()
    await peerRow(h, woken(A, 2))
    live(h, woken(A, 2))
    await h.turn('t1', undefined, woken(A, 2))
    await request(h, 't1').done
    await flush(h)
    expect(releases(h)).toEqual([{ session: SID, items: [{ id: A, attempt: 2, present: false }] }])
    // The next step waits at a fence; the full attempt 3 is appended meanwhile.
    await arm(h, 1, 1)
    const second = request(h, 't1', 1)
    await flush(h)
    expect(second.isMade()).toBe(false)
    await peerRow(h, delivered(A, 3), 'delivery')
    live(h, woken(A, 2), delivered(A, 3))
    await answer(h, { t: 'proceed', fence: 1 })
    await second.done
    expect(admits(h)).toEqual([])
    await answer(h, { t: 'disarm', fence: 1 })
    await request(h, 't1', 2).done
    expect(admits(h)).toEqual([{ session: SID, ids: [A] }])
  })

  test('a wake seen before a reload, its body retained from before the module: the scan counts that body, and the wake is admitted', async () => {
    const kept = new Map<string, unknown>()
    await observing({ sessionState: kept })
    const after = harness({ env: MARKED, sessionState: kept, messages: [{ type: 'user' }] })
    after.setApiConversation([
      { role: 'user', content: [{ type: 'text', text: delivered(A) }] },
      { role: 'user', content: [{ type: 'text', text: woken(A, 2) }] },
    ])
    await after.start()
    // The retry's wake comes in before the child's bootstrap (and its scan).
    await peerRow(after, woken(A, 2))
    after.children[0]!.write(bootstrap(G2, '/tmp/s/bridge/h100.sock', 100))
    await flush(after)
    await after.turn('t1', undefined, 'go')
    await request(after, 't1').done
    expect(admits(after)).toEqual([{ session: SID, ids: [A] }])
    expect(releases(after)).toEqual([])
  })

  test('a wake once judged bodiless is released present false even when a body shows up for the release: its retry is the full body, admitted', async () => {
    const kept = new Map<string, unknown>()
    await observing({ sessionState: kept })
    const after = harness({ env: MARKED, sessionState: kept, messages: [{ type: 'user' }] })
    after.setApiConversation([
      { role: 'user', content: [{ type: 'text', text: delivered(A) }] },
      { role: 'user', content: [{ type: 'text', text: woken(A, 2) }] },
    ])
    // The scan fails at the bootstrap and again at the request: no evidence of the body before the module.
    after.failApiReads(2)
    await after.start()
    await peerRow(after, woken(A, 2))
    after.children[0]!.write(bootstrap(G2, '/tmp/s/bridge/h100.sock', 100))
    await flush(after)
    await after.turn('t1', undefined, 'go')
    await request(after, 't1').done
    await flush(after)
    expect(admits(after)).toEqual([])
    expect(releases(after)).toEqual([{ session: SID, items: [{ id: A, attempt: 2, present: false }] }])
    // The full retry: admitted on its own row.
    await after.complete('t1')
    await peerRow(after, delivered(A, 3))
    after.setApiConversation([
      { role: 'user', content: [{ type: 'text', text: delivered(A) }] },
      { role: 'user', content: [{ type: 'text', text: woken(A, 2) }] },
      { role: 'user', content: [{ type: 'text', text: delivered(A, 3) }] },
    ])
    await after.turn('t2', undefined, delivered(A, 3))
    await request(after, 't2').done
    expect(admits(after)).toEqual([{ session: SID, ids: [A] }])
    expect(releases(after)).toHaveLength(1)
  })

  test('the plain case: stop, release with the body retained, the wake admitted at attempt 2', async () => {
    const h = await observing()
    await peerRow(h, delivered(A))
    live(h, delivered(A))
    await h.turn('t1', undefined, delivered(A))
    await arm(h, 1, 1)
    const r = request(h, 't1')
    await flush(h)
    await answer(h, { t: 'stop', fence: 1, reason: 'reaped' })
    await r.done
    await h.complete('t1')
    await answer(h, { t: 'disarm', fence: 1 })
    expect(releases(h)).toEqual([{ session: SID, items: [{ id: A, attempt: 1, present: true }] }])
    await peerRow(h, woken(A, 2))
    live(h, delivered(A), woken(A, 2))
    await h.turn('t2', undefined, woken(A, 2))
    await request(h, 't2').done
    expect(admits(h)).toEqual([{ session: SID, ids: [A] }])
    expect(releases(h)).toHaveLength(1)
  })

  test('a wake with its body still above is admitted; a release says present only for a body, never for a wake alone', async () => {
    const h = await observing()
    await peerRow(h, delivered(A))
    await peerRow(h, woken(A, 2))
    live(h, delivered(A), woken(A, 2))
    await h.turn('t1', undefined, woken(A, 2))
    await request(h, 't1').done
    expect(admits(h)).toEqual([{ session: SID, ids: [A] }])
  })

  test("the activation's retained names only receipts whose body the conversation holds", async () => {
    const h = harness({ env: MARKED, messages: [{ type: 'user' }] })
    h.setApiConversation([{ role: 'user', content: [{ type: 'text', text: `${woken(A, 2)}\n${delivered(B)}` }] }])
    await h.start()
    h.children[0]!.write(bootstrap())
    await flush(h)
    expect(h.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, launch: String(h.sessionState.get('launch')), retained: [B] }])
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

  test('a released receipt is not an admitted one: stop, release, the retry in this launch, its admission reported', async () => {
    const h = await stopped()
    await h.complete('t1')
    await answer(h, { t: 'disarm', fence: 1 })
    expect(releases(h)).toEqual([{ session: SID, items: [{ id: A, attempt: 2, present: true }] }])
    await flush(h)
    // The deliverer's retry: a wake naming the next attempt, then a turn.
    await peerRow(h, delivered(A, 3, 'wake'))
    live(h, delivered(A, 2), delivered(A, 3, 'wake'))
    await h.turn('t2', undefined, delivered(A, 3, 'wake'))
    await request(h, 't2').done
    expect(admits(h)).toEqual([{ session: SID, ids: [A] }])
  })

  test('a release waiting for its replay is held again by a newer fence: it goes once no fence holds, its row read afresh', async () => {
    let fail = true
    const h = await stopped({ holderAnswer: (b) => (b.kind === 'release' && fail ? 'fail' : undefined) })
    await answer(h, { t: 'disarm', fence: 1 })
    const tried = releases(h).length
    expect(tried).toBeGreaterThan(0)
    expect(releases(h).at(-1)).toEqual({ session: SID, items: [{ id: A, attempt: 2, present: true }] })
    // Fence 2 installs before the replay: the replay sends nothing while it stands.
    await arm(h, 2, 2)
    fail = false
    await h.fire(HOLDER_RETRY_MS)
    expect(releases(h)).toHaveLength(tried)
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [{ session: SID, id: A, attempt: 2 }] })
    // Its disarm: released now, the row's presence read again (a rewind took it out).
    live(h)
    await answer(h, { t: 'disarm', fence: 2 })
    expect(releases(h)).toHaveLength(tried + 1)
    expect(releases(h).at(-1)).toEqual({ session: SID, items: [{ id: A, attempt: 2, present: false }] })
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [] })
  })

  test('a release in flight when a newer fence installs is not sent again under it: one attempt per check, the receipt kept stopped until no fence holds', async () => {
    const h = await stopped({ holderAnswer: (b) => (b.kind === 'release' ? 'hold' : undefined) })
    await answer(h, { t: 'disarm', fence: 1 })
    expect(releases(h)).toHaveLength(1)
    // Fence 2 installs while that POST is in flight; then it fails.
    await arm(h, 2, 2)
    h.holderPosts.find((p) => p.body.kind === 'release')!.fail()
    await flush(h)
    expect(releases(h)).toHaveLength(1)
    await h.fire(HOLDER_RETRY_MS)
    expect(releases(h)).toHaveLength(1)
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [{ session: SID, id: A, attempt: 2 }] })
    live(h)
    await answer(h, { t: 'disarm', fence: 2 })
    expect(releases(h)).toHaveLength(2)
    expect(releases(h).at(-1)).toEqual({ session: SID, items: [{ id: A, attempt: 2, present: false }] })
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

  test("a report the child answers pending (its activation not settled) is replayed, never taken for the process's refusal", async () => {
    let pending = true
    const h = await observing({ holderAnswer: (b) => (b.kind === 'admit' && pending ? { status: 200, body: { ok: false, code: 'pending', error: 'not activated yet' } } : undefined) })
    await peerRow(h, delivered(A))
    live(h, delivered(A))
    await h.turn('t1', undefined, delivered(A))
    await request(h, 't1').done
    await flush(h)
    expect(keptReceipts(h)).toEqual({ reports: [{ kind: 'admit', session: SID, ids: [A] }], stopped: [] })
    pending = false
    await h.fire(HOLDER_RETRY_MS)
    expect(admits(h).at(-1)).toEqual({ session: SID, ids: [A] })
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [] })
  })

  test('a storage answer that names no state for an id leaves it to be replayed: only an explicit outcome ends one', async () => {
    let storage = true
    const h = await observing({
      holderAnswer: (b) => (storage && (b.kind === 'admit' || b.kind === 'release') ? { status: 200, body: { ok: false, code: 'storage', error: 'disk', receipts: b.kind === 'admit' ? { [A]: 'admitted' } : {} } } : undefined),
    })
    await peerRow(h, delivered(A))
    await peerRow(h, delivered(B))
    live(h, delivered(A), delivered(B))
    await h.turn('t1', undefined, 'go')
    await h.complete('t1')
    await h.turn('t2', undefined, 'go')
    await request(h, 't2').done
    await flush(h)
    expect(keptReceipts(h)).toMatchObject({ reports: [{ kind: 'admit', session: SID, ids: [B] }] })
    storage = false
    await h.fire(HOLDER_RETRY_MS)
    expect(admits(h).at(-1)).toEqual({ session: SID, ids: [B] })
    expect(keptReceipts(h)).toEqual({ reports: [], stopped: [] })
  })

  test("a first scan that failed is tried again by a later request: a reload's earlier receipts are still admitted", async () => {
    const kept = new Map<string, unknown>()
    await observing({ sessionState: kept })
    const after = harness({ env: MARKED, sessionState: kept, messages: [{ type: 'user' }] })
    after.setApiConversation([{ role: 'user', content: [{ type: 'text', text: delivered(A) }] }])
    after.failApiReads(1)
    await after.start()
    after.children[0]!.write(bootstrap(G2, '/tmp/s/bridge/h100.sock', 100))
    await flush(after)
    await request(after, 't0').done
    await request(after, 't0', 1).done
    expect(admits(after)).toEqual([{ session: SID, ids: [A] }])
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
    expect(h.holderBodies('ready')).toEqual([{ kind: 'ready', generation: G2, upgrade: true, observe: true }])
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

  test("a fresh process is one whose own SessionStart (a startup, a resume, a fork) this module handled, seconds into its run; a module loaded with none (a reload) takes it for an existing one, legacy and unobserved", async () => {
    for (const source of ['startup', 'resume', 'fork'] as const) {
      const fresh = harness({ env: MARKED, messages: [{ type: 'user' }], processStart: source })
      await fresh.start()
      fresh.children[0]!.write(bootstrap(GEN, ROUTE, 99, 2.5))
      await flush(fresh)
      expect(fresh.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, launch: String(fresh.sessionState.get('launch')), retained: [] }])
      expect(fresh.sessionState.get('holder')).toMatchObject({ observerStarted: true, fresh: true })
    }
    // A SessionStart in a process long running, or of an age unknown, is no first load.
    for (const age of [3600, null]) {
      const aged = harness({ env: MARKED, messages: [{ type: 'user' }], processStart: 'startup' })
      await aged.start()
      aged.children[0]!.write(bootstrap(GEN, ROUTE, 99, age))
      await flush(aged)
      expect(aged.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, upgrade: true, observe: false }])
      expect(aged.sessionState.get('holder')).toMatchObject({ observerStarted: false, fresh: false })
    }
    // Loaded with no SessionStart of its own (a reload, nothing a module before
    // kept): it waits for one a while, then the process is an existing one;
    // its age, a second, decides nothing; a /clear's SessionStart is no start.
    const old = harness({ env: MARKED, messages: [{ type: 'user' }], processStart: null })
    await old.start()
    old.children[0]!.write(bootstrap(GEN, ROUTE, 99, 1))
    await flush(old)
    await old.classicStart('clear')
    await flush(old)
    expect(old.holderBodies('ready')).toEqual([])
    await old.fire(STARTUP_WAIT_MS)
    expect(old.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, upgrade: true, observe: false }])
    expect(old.sessionState.get('holder')).toMatchObject({ observerStarted: false, fresh: false })
  })

  test("a mid-process /resume reaching a reloaded module with no trace, in an old process, before it decided: an existing process", async () => {
    const h = harness({ env: MARKED, messages: [{ type: 'user' }], processStart: null })
    await h.start()
    h.children[0]!.write(bootstrap(GEN, ROUTE, 99, 3600))
    await flush(h)
    await h.classicStart('resume')
    await flush(h)
    expect(h.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, upgrade: true, observe: false }])
    expect(h.sessionState.get('holder')).toMatchObject({ observerStarted: false, fresh: false })
  })

  test("the age is the process's at its SessionStart: one sampled at 59 s with the SessionStart 4 s later is an existing process; 50 s and 4 s, a fresh one", async () => {
    const late = harness({ env: MARKED, messages: [{ type: 'user' }], processStart: null })
    await late.start()
    late.children[0]!.write(bootstrap(GEN, ROUTE, 99, 59))
    await flush(late)
    late.advance(4_000)
    await late.classicStart('resume')
    await flush(late)
    expect(late.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, upgrade: true, observe: false }])
    expect(late.sessionState.get('holder')).toMatchObject({ observerStarted: false, fresh: false })
    const young = harness({ env: MARKED, messages: [{ type: 'user' }], processStart: null })
    await young.start()
    young.children[0]!.write(bootstrap(GEN, ROUTE, 99, 50))
    await flush(young)
    young.advance(4_000)
    await young.classicStart('startup')
    await flush(young)
    expect(young.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, launch: String(young.sessionState.get('launch')), retained: [] }])
  })

  test("the process's SessionStart coming after the child's bootstrap still makes it a fresh one", async () => {
    const h = harness({ env: MARKED, messages: [{ type: 'user' }], processStart: null })
    await h.start()
    h.children[0]!.write(bootstrap())
    await flush(h)
    expect(h.holderBodies('ready')).toEqual([])
    await h.classicStart('startup')
    await flush(h)
    expect(h.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, launch: String(h.sessionState.get('launch')), retained: [] }])
  })

  test('a process a module before this one ran in with no observer (its launch kept) stays legacy and unobserved, however young', async () => {
    const pre = harness({ env: MARKED, sessionState: new Map<string, unknown>([['launch', 'LaunchLaunchLaunchLaun']]), messages: [{ type: 'user' }] })
    await pre.start()
    pre.children[0]!.write(bootstrap())
    await flush(pre)
    expect(pre.holderBodies('ready')).toEqual([{ kind: 'ready', generation: GEN, upgrade: true, observe: false }])
    expect(pre.sessionState.get('holder')).toMatchObject({ observerStarted: false })
  })

  test("a reload keeps the process's classification: a fresh one's next module activates whatever the age; an existing one's stays unobserved", async () => {
    const kept = new Map<string, unknown>()
    await observing({ sessionState: kept })
    const after = harness({ env: MARKED, sessionState: kept, messages: [{ type: 'user' }] })
    await after.start()
    after.children[0]!.write(bootstrap(G2, ROUTE, 99, 3600))
    await flush(after)
    expect(after.holderBodies('ready')).toEqual([{ kind: 'ready', generation: G2, launch: String(kept.get('launch')), retained: [] }])
    const old = new Map<string, unknown>()
    const first = harness({ env: MARKED, sessionState: old, messages: [{ type: 'user' }], processStart: null })
    await first.start()
    first.children[0]!.write(bootstrap(GEN, ROUTE, 99, 3600))
    await flush(first)
    await first.fire(STARTUP_WAIT_MS)
    // Its next module, even one that handled a SessionStart, keeps the word.
    const next = harness({ env: MARKED, sessionState: old, messages: [{ type: 'user' }] })
    await next.start()
    next.children[0]!.write(bootstrap(G2, ROUTE, 99, 1))
    await flush(next)
    expect(next.holderBodies('ready')).toEqual([{ kind: 'ready', generation: G2, upgrade: true, observe: false }])
  })
})

describe('receipts: a /clear (O12 M4b)', () => {
  test("a request in a /clear's window, before the bridge has moved to the new session, reports the conversation it read: the new one", async () => {
    const h = await observing()
    await h.hook('session.end', {})(h.engine, { reason: 'clear', sessionId: SID }, async () => ({}))
    await flush(h)
    // The engine is on the new conversation; the bridge's poll has not moved yet.
    h.setSession(NEW)
    await peerRow(h, delivered(C))
    live(h, delivered(C))
    await h.turn('t2', undefined, delivered(C))
    await request(h, 't2').done
    expect(admits(h)).toEqual([{ session: NEW, ids: [C] }])
  })

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
