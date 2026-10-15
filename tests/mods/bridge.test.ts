import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import { HEARTBEAT_MS, TEXT_CAP, registerBridge, resetBridge, splitLines } from '../../hooks/mods/bridge'

tier('user')

const SID = '5b000001-0000-4000-8000-00000000005b'
const SOCK = `/tmp/s/bridge/${SID}.sock`
const hello = (session = SID, socket = SOCK) => `${JSON.stringify({ op: 'hello', session, pid: 7, socket, protocol: 1 })}\n`
const line = (obj: Record<string, unknown>) => `${JSON.stringify(obj)}\n`

describe('splitLines', () => {
  test('cuts whole lines and keeps the unfinished rest', async () => {
    expect(splitLines('', 'a\nb\nc')).toEqual({ lines: ['a', 'b'], rest: 'c' })
    expect(splitLines('c', 'd\n')).toEqual({ lines: ['cd'], rest: '' })
    expect(splitLines('', '\n\n')).toEqual({ lines: [], rest: '' })
  })
})

type Handler = (...args: unknown[]) => unknown
type Matcher = Record<string, unknown> | undefined
type Piece = { stream: 'stdout' | 'stderr'; text: string }

/** A child as `$.process.spawn` streams it: the test writes its output and ends it. */
function fakeChild(argv: readonly string[]) {
  const queued: (Piece | null)[] = []
  let wake: (() => void) | undefined
  let ended = false
  let killed = false
  const push = (p: Piece | null) => {
    queued.push(p)
    wake?.()
  }
  const iterator = {
    argv,
    get killed() {
      return killed
    },
    write: (text: string) => push({ stream: 'stdout', text }),
    end: () => push(null),
    result: Promise.resolve({ code: 0, signal: null }),
    async next(): Promise<IteratorResult<Piece>> {
      for (;;) {
        if (ended) {
          return { done: true, value: undefined }
        }
        const p = queued.shift()
        if (p === null) {
          ended = true
          continue
        }
        if (p !== undefined) {
          return { done: false, value: p }
        }
        await new Promise<void>((resolve) => (wake = resolve))
      }
    },
    async return(): Promise<IteratorResult<Piece>> {
      killed = true
      ended = true
      wake?.()
      return { done: true, value: undefined }
    },
    [Symbol.asyncIterator]() {
      return this
    },
  }
  return iterator
}

/**
 * The hooks as register.tsx registers them, and an engine of plain records:
 * spawned children, posts (each released by the test when `hold` is set),
 * timers fired by hand.
 */
function harness(options: { env?: Record<string, string>; hold?: boolean; failAt?: number[] } = {}) {
  const hooks: { event: string; matcher: Matcher; handler: Handler }[] = []
  const on = ((event: string, ...rest: unknown[]) => {
    const handler = rest[rest.length - 1] as Handler
    const matcher = rest.length > 1 ? (rest[0] as Matcher) : undefined
    hooks.push({ event, matcher, handler })
    return { catch: () => undefined }
  }) as unknown as On
  const children: ReturnType<typeof fakeChild>[] = []
  const posts: { url: string; socketPath?: string; events: Record<string, unknown>[]; release: () => void; fail: () => void }[] = []
  const timers: { kind: 'after' | 'every'; ms: number; fn: () => void; cancelled: boolean }[] = []
  const logs: string[] = []
  let session = SID
  const $ = {
    plugin: { name: 'doperpowers', root: '/plug' },
    env: { get: async (name: string) => options.env?.[name] },
    session: {
      id: async () => session,
      model: async () => 'claude-haiku',
      version: async () => ({ version: '2.1.300' }),
      usage: async () => ({ startedAt: 0, context: { tokens: 5000, window: 200000, percent: 2 }, rateLimits: [] }),
    },
    process: {
      spawn: (request: { argv: readonly string[] }) => {
        const child = fakeChild(request.argv)
        children.push(child)
        return child
      },
    },
    http: {
      fetch: (url: string, init: { socketPath?: string; body?: string }) =>
        new Promise((resolve, reject) => {
          const release = () => resolve({ status: 204, ok: true, headers: {}, text: '' })
          const fail = () => reject(new Error('refused'))
          const n = posts.length
          posts.push({ url, socketPath: init.socketPath, events: JSON.parse(init.body ?? '[]'), release, fail })
          if (!options.hold) {
            ;(options.failAt?.includes(n) ? fail : release)()
          }
        }),
    },
    clock: {
      after: (ms: number, fn: () => void) => {
        const t = { kind: 'after' as const, ms, fn, cancelled: false }
        timers.push(t)
        return { cancel: () => (t.cancelled = true) }
      },
      every: (ms: number, fn: () => void) => {
        const t = { kind: 'every' as const, ms, fn, cancelled: false }
        timers.push(t)
        return { cancel: () => (t.cancelled = true) }
      },
    },
    ui: { log: (text: string) => logs.push(text) },
  }
  resetBridge()
  registerBridge(on)
  const engine = $ as unknown as EngineInterface
  const hook = (event: string, e: Record<string, unknown> = {}) => {
    const found = hooks.filter((h) => h.event === event && Object.entries(h.matcher ?? {}).every(([k, v]) => (v instanceof RegExp ? v.test(String(e[k])) : e[k] === v)))
    if (found.length !== 1) {
      throw new Error(`${found.length} hooks for ${event}`)
    }
    return found[0]!.handler
  }
  const settle = async () => {
    for (let i = 0; i < 30; i++) {
      await Promise.resolve()
    }
  }
  const events = () => posts.flatMap((p) => p.events)
  const ofType = (type: string) => events().filter((e) => e.type === type)
  const start = async () => {
    await hook('session.start', { cwd: '/w' })(engine, { cwd: '/w', surface: 'terminal', isInteractive: true }, async () => ({ cwd: '/w' }))
    await settle()
  }
  const ready = async () => {
    await start()
    children[0]!.write(hello())
    await settle()
  }
  /** Runs a turn.step hook over these chunks, collecting what it yields. */
  const step = async (e: Record<string, unknown>, chunks: Record<string, unknown>[], during?: () => Promise<void>) => {
    const result = { turnId: e.turnId, index: e.index, answer: 'x', toolUses: [], stopReason: 'end_turn', usage: null }
    const next = () => {
      const gen = (async function* () {
        for (const c of chunks) {
          yield c
        }
        await during?.()
        return result
      })() as AsyncGenerator<Record<string, unknown>, unknown> & { result: Promise<unknown> }
      gen.result = Promise.resolve(result)
      return gen
    }
    const gen = hook('turn.step', e)(engine, e, next) as AsyncGenerator<Record<string, unknown>, unknown>
    const yielded: Record<string, unknown>[] = []
    for (;;) {
      const r = await gen.next()
      if (r.done) {
        await settle()
        return { yielded, returned: r.value }
      }
      yielded.push(r.value)
    }
  }
  return {
    engine,
    hook,
    children,
    posts,
    timers,
    logs,
    settle,
    events,
    ofType,
    start,
    ready,
    step,
    setSession: (id: string) => (session = id),
  }
}

describe('the child', () => {
  test('is spawned at session start as `sminos bridge --session <id>` from the plugin', async () => {
    const h = harness()
    await h.start()
    expect(h.children.length).toBe(1)
    expect(h.children[0]!.argv).toEqual(['/plug/skills/sminos/scripts/sminos', 'bridge', '--session', SID])
  })

  test('nothing is posted before its hello; then the session start, then a resync holding what happened meanwhile, to the socket hello names', async () => {
    const h = harness()
    await h.start()
    await h.hook('turn.start', { turnId: 't1' })(h.engine, { turnId: 't1', text: 'hi' }, async () => ({ turnId: 't1' }))
    await h.settle()
    expect(h.posts.length).toBe(0)
    h.children[0]!.write(hello())
    await h.settle()
    expect(h.posts[0]!.url).toBe('http://bridge/events')
    expect(h.posts[0]!.socketPath).toBe(SOCK)
    expect(h.events().map((e) => e.type)).toEqual(['session', 'resync'])
    expect(h.events()[0]).toMatchObject({ phase: 'start', session: SID, cwd: '/w', model: 'claude-haiku', version: '2.1.300', isInteractive: true })
    expect(h.events()[1]).toMatchObject({ turns: [{ turnId: 't1', agentId: null }], streaming: [], agents: [] })
  })

  test('an internal fork (SMNS_INTERNAL) gets no bridge', async () => {
    const h = harness({ env: { SMNS_INTERNAL: '1' } })
    await h.start()
    expect(h.children.length).toBe(0)
  })

  test('a child that ends is followed by a new one, later each time it ends at once', async () => {
    const h = harness()
    await h.start()
    h.children[0]!.end()
    await h.settle()
    const first = h.timers.filter((t) => t.kind === 'after')
    expect(first.map((t) => t.ms)).toEqual([1000])
    first[0]!.fn()
    await h.settle()
    expect(h.children.length).toBe(2)
    expect(h.children[1]!.argv).toEqual(h.children[0]!.argv)
    h.children[1]!.end()
    await h.settle()
    expect(h.timers.filter((t) => t.kind === 'after').map((t) => t.ms)).toEqual([1000, 2000])
  })

  test('a session whose id changed (a /clear) gets a child under the new id, the old one stopped', async () => {
    const h = harness()
    await h.ready()
    const beat = h.timers.find((t) => t.kind === 'every')!
    expect(beat.ms).toBe(HEARTBEAT_MS)
    const NEW = '6c000002-0000-4000-8000-00000000006c'
    h.setSession(NEW)
    beat.fn()
    await h.settle()
    expect(h.children[0]!.killed).toBe(true)
    expect(h.children[1]!.argv).toEqual(['/plug/skills/sminos/scripts/sminos', 'bridge', '--session', NEW])
    // The stopped child is not respawned.
    expect(h.timers.filter((t) => t.kind === 'after').length).toBe(0)
  })

  test('the heartbeat carries the turn state', async () => {
    const h = harness()
    await h.ready()
    h.timers.find((t) => t.kind === 'every')!.fn()
    await h.settle()
    expect(h.ofType('heartbeat')[0]).toMatchObject({ state: { mainTurn: null, isStreaming: false, tools: [] } })
  })
})

describe('commands', () => {
  test('a line split across pieces is answered once whole: ping, with the turn state', async () => {
    const h = harness()
    await h.ready()
    h.children[0]!.write('{"id":"c1",')
    await h.settle()
    expect(h.ofType('result').length).toBe(0)
    h.children[0]!.write('"op":"ping"}\n')
    await h.settle()
    expect(h.ofType('result')[0]).toMatchObject({ id: 'c1', op: 'ping', ok: true, result: { pong: true, state: { mainTurn: null, isStreaming: false } } })
  })

  test('mid-turn, mid-model and mid-tool, ping says so', async () => {
    const h = harness()
    await h.ready()
    await h.hook('turn.start', { turnId: 't1' })(h.engine, { turnId: 't1', text: 'go' }, async () => ({ turnId: 't1' }))
    // During a model request of the main loop.
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'a' }], async () => {
      h.children[0]!.write(line({ id: 'c2', op: 'ping' }))
      await h.settle()
    })
    expect(h.ofType('result')[0]).toMatchObject({ id: 'c2', result: { state: { mainTurn: 't1', isStreaming: true } } })
    // During a Bash call.
    await h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: 'tu1', command: 'sleep' }, async () => {
      h.children[0]!.write(line({ id: 'c3', op: 'ping' }))
      await h.settle()
      return { text: 'done' }
    })
    await h.settle()
    expect(h.ofType('result')[1]).toMatchObject({ id: 'c3', result: { state: { mainTurn: 't1', isStreaming: false, tools: ['Bash'] } } })
  })

  test('an op the mod does not know is refused, saying which', async () => {
    const h = harness()
    await h.ready()
    h.children[0]!.write(line({ id: 'c4', op: 'levitate' }))
    await h.settle()
    expect(h.ofType('result')[0]).toMatchObject({ id: 'c4', op: 'levitate', ok: false, error: 'unknown op: levitate' })
  })

  test('a line that is not JSON is passed by', async () => {
    const h = harness()
    await h.ready()
    h.children[0]!.write('garbage\n')
    h.children[0]!.write(line({ id: 'c5', op: 'ping' }))
    await h.settle()
    expect(h.ofType('result').map((e) => e.id)).toEqual(['c5'])
  })
})

describe('the stream', () => {
  test('turn.step: each chunk tagged with turn, agent, step and its index, the engine items left out; the stream passes unchanged', async () => {
    const h = harness()
    await h.ready()
    const chunks = [
      { kind: 'engine', ref: 1 },
      { kind: 'thinking', index: 0, text: 'hm' },
      { kind: 'text', index: 1, text: 'Hel' },
      { kind: 'text', index: 1, text: 'lo' },
      { kind: 'stop', stopReason: 'end_turn', usage: null },
    ]
    const { yielded, returned } = await h.step({ turnId: 't1', index: 2, model: 'm', effort: 'high', messageCount: 4 }, chunks)
    expect(yielded).toEqual(chunks)
    expect(returned).toMatchObject({ turnId: 't1', stopReason: 'end_turn' })
    const sent = h.ofType('chunk')
    expect(sent.map((e) => e.chunkIndex)).toEqual([0, 1, 2, 3])
    expect(sent[2]).toMatchObject({ turnId: 't1', agentId: null, step: 2, chunkIndex: 2, chunk: { kind: 'text', index: 1, text: 'lo' } })
    expect(h.ofType('step').map((e) => e.phase)).toEqual(['start', 'end'])
    expect(h.ofType('step')[0]).toMatchObject({ model: 'm', effort: 'high', messageCount: 4 })
    expect(h.ofType('step')[1]).toMatchObject({ stopReason: 'end_turn' })
  })

  test("a subagent's chunks carry its agentId", async () => {
    const h = harness()
    await h.ready()
    await h.step({ turnId: 'ts', index: 0, model: 'm', messageCount: 1, agentId: 'a7' }, [{ kind: 'text', index: 0, text: 'sub' }])
    expect(h.ofType('chunk')[0]).toMatchObject({ agentId: 'a7', turnId: 'ts', chunk: { text: 'sub' } })
  })

  test('one post in flight at a time; what comes meanwhile goes in the next, in order', async () => {
    const h = harness({ hold: true })
    await h.start()
    h.children[0]!.write(hello())
    await h.settle()
    expect(h.posts.length).toBe(1)
    await h.hook('turn.start', { turnId: 't1' })(h.engine, { turnId: 't1', text: '' }, async () => ({ turnId: 't1' }))
    await h.hook('turn.start', { turnId: 't2' })(h.engine, { turnId: 't2', text: '', agentId: 'a1' }, async () => ({ turnId: 't2' }))
    await h.settle()
    expect(h.posts.length).toBe(1)
    h.posts[0]!.release()
    await h.settle()
    expect(h.posts.length).toBe(2)
    expect(h.posts[1]!.events.map((e) => e.turnId)).toEqual(['t1', 't2'])
  })

  test('a post lost mid-message: the next opens with the gap and a resync whose text covers its upTo', async () => {
    const h = harness({ hold: true })
    await h.start()
    h.children[0]!.write(hello())
    await h.settle()
    h.posts[0]!.release()
    await h.settle()
    const e = { turnId: 't1', index: 0, model: 'm', messageCount: 1 }
    const tag = { turnId: 't1', agentId: null, step: 0 }
    const gen = h.hook('turn.step', e)(h.engine, e, () => {
      const g = (async function* () {
        yield { kind: 'text', index: 0, text: 'A' }
        yield { kind: 'text', index: 0, text: 'B' }
        yield { kind: 'text', index: 0, text: 'C' }
        return { turnId: 't1', index: 0, answer: 'ABC', toolUses: [], stopReason: 'end_turn', usage: null }
      })() as AsyncGenerator<unknown, unknown> & { result: Promise<unknown> }
      g.result = Promise.resolve({ turnId: 't1', index: 0, stopReason: 'end_turn', usage: null })
      return g
    }) as AsyncGenerator<unknown, unknown>
    await gen.next() // step start posted (1); A queued
    await h.settle()
    h.posts[1]!.release()
    await h.settle()
    expect(h.posts[2]!.events).toMatchObject([{ type: 'chunk', ...tag, chunkIndex: 0 }])
    await gen.next() // B queued behind the post of A
    await h.settle()
    h.posts[2]!.fail() // A and B never reach the child
    await h.settle()
    expect(h.posts.length).toBe(3) // the next post waits
    h.timers.filter((t) => t.kind === 'after').at(-1)!.fn()
    await h.settle()
    const resent = h.posts[3]!.events
    expect(resent[0]).toMatchObject({ type: 'gap', dropped: 2 })
    expect(resent[1]).toMatchObject({ type: 'resync', streaming: [{ ...tag, text: 'AB', upTo: 1 }] })
    h.posts[3]!.release()
    await gen.next() // C follows the resync
    await h.settle()
    expect(h.posts[4]!.events).toMatchObject([{ type: 'chunk', ...tag, chunkIndex: 2, chunk: { text: 'C' } }])
  })

  test('a child replaced mid-message gets the message so far in its first post', async () => {
    const h = harness()
    await h.ready()
    await h.step({ turnId: 't0', index: 0, model: 'm', messageCount: 1 }, [], async () => {
      // Mid-message: the child dies and the next says hello.
      await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1, agentId: 'a1' }, [{ kind: 'text', index: 0, text: 'Hel' }], async () => {
        h.children[0]!.end()
        await h.settle()
        h.timers.filter((t) => t.kind === 'after').at(-1)!.fn()
        await h.settle()
        h.children[1]!.write(hello())
        await h.settle()
        const first = h.posts.at(-1)!.events
        expect(first.map((e) => e.type)).toEqual(['session', 'resync'])
        expect(first[1]).toMatchObject({ streaming: [{ turnId: 't0', agentId: null, step: 0, text: '', upTo: -1 }, { turnId: 't1', agentId: 'a1', step: 0, text: 'Hel', upTo: 0 }] })
      })
    })
  })

  test('tool calls and their results; every string capped at any depth, and each cut flagged', async () => {
    const h = harness()
    await h.ready()
    const long = 'x'.repeat(TEXT_CAP + 10)
    const edits = [{ old_string: long, new_string: 'y' }]
    await h.hook('tool.call', { tool: 'MultiEdit' })(h.engine, { tool: 'MultiEdit', tool_use_id: 'tu9', agentId: 'a1', file_path: '/f', edits }, async () => ({ text: long, isError: false }))
    await h.settle()
    const [call, result] = h.ofType('tool')
    expect(call).toMatchObject({ phase: 'call', toolUseId: 'tu9', tool: 'MultiEdit', agentId: 'a1', input: { file_path: '/f', edits: [{ new_string: 'y' }] }, truncated: true })
    const input = call!.input as { edits: { old_string: string }[] }
    expect(input.edits[0]!.old_string.length).toBe(TEXT_CAP)
    expect(Object.keys(input).sort()).toEqual(['edits', 'file_path'])
    expect(result).toMatchObject({ phase: 'result', toolUseId: 'tu9', isError: false, truncated: true })
    expect(String(result!.text).length).toBe(TEXT_CAP)
  })

  test('a denied call is reported denied; a long denial and a long prompt are cut and flagged', async () => {
    const h = harness()
    await h.ready()
    await h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: 'tu2', command: 'rm' }, async () => ({ deny: 'no' }))
    await h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: 'tu3', command: 'rm' }, async () => ({ deny: 'n'.repeat(TEXT_CAP + 1) }))
    await h.hook('turn.start', { turnId: 't1' })(h.engine, { turnId: 't1', text: 'p'.repeat(TEXT_CAP + 1) }, async () => ({ turnId: 't1' }))
    await h.settle()
    const tools = h.ofType('tool')
    expect(tools[1]).toMatchObject({ phase: 'result', denied: 'no' })
    expect(tools[1]!.truncated).toBeUndefined()
    expect(tools[3]).toMatchObject({ phase: 'result', truncated: true })
    expect(String(tools[3]!.denied).length).toBe(TEXT_CAP)
    expect(h.ofType('turn')[0]).toMatchObject({ phase: 'start', truncated: true })
    expect(String(h.ofType('turn')[0]!.text).length).toBe(TEXT_CAP)
  })

  test('subagents: spawned and stopped', async () => {
    const h = harness()
    await h.ready()
    const spawn = { tool_use_id: 'tu3', prompt: 'p', description: 'scout', subagentType: 'Explore', background: true, fork: false, parentModel: 'm', provider: { plugin: 'engine', tier: 'core' } }
    await h.hook('agent.spawn', spawn)(h.engine, spawn, async () => ({ model: 'claude-haiku', agentId: 'a9' }))
    await h.hook('classic.SubagentStop', { hook_event_name: 'SubagentStop' })(h.engine, { hook_event_name: 'SubagentStop', agent_id: 'a9', agent_type: 'Explore' }, async () => ({}))
    await h.settle()
    expect(h.ofType('agent')).toMatchObject([
      { phase: 'spawn', agentId: 'a9', subagentType: 'Explore', description: 'scout', background: true, model: 'claude-haiku', parentAgentId: null },
      { phase: 'stop', agentId: 'a9', agentType: 'Explore' },
    ])
  })

  test("turn boundaries, and the main turn's usage at its end", async () => {
    const h = harness()
    await h.ready()
    await h.hook('turn.start', { turnId: 't1' })(h.engine, { turnId: 't1', text: 'go' }, async () => ({ turnId: 't1' }))
    const usage = { input_tokens: 1, output_tokens: 2, cache_creation_input_tokens: 0, cache_read_input_tokens: 0, model: 'm' }
    await h.hook('turn.complete', { turnId: 't1' })(h.engine, { turnId: 't1', answer: 'ok', durationMs: 1, reason: 'answer', usage }, async () => ({ text: 'ok' }))
    await h.settle()
    expect(h.ofType('turn')).toMatchObject([
      { phase: 'start', turnId: 't1', agentId: null, text: 'go' },
      { phase: 'complete', turnId: 't1', reason: 'answer', usage },
    ])
    expect(h.ofType('usage')[0]).toMatchObject({ context: { tokens: 5000, window: 200000 } })
  })

  test("a /clear: the old child gets the end and nothing after it; the new session's events reach its own child", async () => {
    const h = harness()
    await h.ready()
    await h.hook('turn.start', { turnId: 'old' })(h.engine, { turnId: 'old', text: 'before' }, async () => ({ turnId: 'old' }))
    await h.hook('session.end', {})(h.engine, { reason: 'clear', sessionId: SID }, async () => ({}))
    await h.settle()
    // The new session's first turn, before its id is known.
    await h.hook('turn.start', { turnId: 'new' })(h.engine, { turnId: 'new', text: 'after' }, async () => ({ turnId: 'new' }))
    await h.settle()
    const toOld = () => h.posts.filter((p) => p.socketPath === SOCK).flatMap((p) => p.events)
    expect(toOld().at(-1)).toMatchObject({ type: 'session', phase: 'end', reason: 'clear' })
    expect(toOld().some((e) => e.turnId === 'new')).toBe(false)
    // The id is looked for at once, not at the heartbeat.
    const NEW = '6c000002-0000-4000-8000-00000000006c'
    const NEWSOCK = `/tmp/s/bridge/${NEW}.sock`
    h.setSession(NEW)
    h.timers.filter((t) => t.kind === 'after').at(-1)!.fn()
    await h.settle()
    expect(h.children[0]!.killed).toBe(true)
    expect(h.children[1]!.argv).toEqual(['/plug/skills/sminos/scripts/sminos', 'bridge', '--session', NEW])
    h.children[1]!.write(hello(NEW, NEWSOCK))
    await h.settle()
    const toNew = h.posts.filter((p) => p.socketPath === NEWSOCK).flatMap((p) => p.events)
    expect(toNew.map((e) => e.type)).toEqual(['session', 'resync'])
    expect(toNew[0]).toMatchObject({ phase: 'start', session: NEW })
    expect(toNew[1]).toMatchObject({ turns: [{ turnId: 'new' }] })
    expect(toOld().some((e) => e.turnId === 'new')).toBe(false)
  })

  test('the session end is reported', async () => {
    const h = harness()
    await h.ready()
    await h.hook('session.end', {})(h.engine, { reason: 'prompt_input_exit', sessionId: SID }, async () => ({}))
    await h.settle()
    expect(h.ofType('session').map((e) => e.phase)).toEqual(['start', 'end'])
    expect(h.ofType('session')[1]).toMatchObject({ reason: 'prompt_input_exit' })
  })
})
