import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import { ASK_TOOL } from '../../hooks/mods/ask'
import {
  BACKGROUND_WINDOW_MS,
  HEARTBEAT_MS,
  RECORD_WAIT_MS,
  ROWS_POLLS,
  ROWS_POLL_MS,
  STEER_WAKE,
  STEP_END_WAIT_MS,
  TRANSCRIPT_RETRY_MS,
  TEXT_CAP,
  compacted,
  onAskNote,
  registerBridge,
  resetBridge,
  splitLines,
} from '../../hooks/mods/bridge'

tier('user')

const SID = '5b000001-0000-4000-8000-00000000005b'
const SOCK = `/tmp/s/bridge/${SID}.sock`
const NONCE = 'n0'
const hello = (session = SID, socket = SOCK, kept?: Record<string, unknown>, nonce = NONCE, seed?: Record<string, string>) =>
  `${JSON.stringify({ op: 'hello', session, pid: 7, socket, protocol: 1, nonce, ...(kept !== undefined && { kept }), ...(seed !== undefined && { seed }) })}\n`
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
function harness(
  options: {
    env?: Record<string, string>
    hold?: boolean
    failAt?: number[]
    holdAppend?: boolean
    taskStopFails?: string[]
    denyAppend?: string
    /** What `$.session.messages()` answers at load: none, a session the module starts with; some, a reload or a resume. */
    messages?: unknown[]
  } = {},
) {
  const hooks: { event: string; matcher: Matcher; handler: Handler }[] = []
  const on = ((event: string, ...rest: unknown[]) => {
    const handler = rest[rest.length - 1] as Handler
    const matcher = rest.length > 1 ? (rest[0] as Matcher) : undefined
    hooks.push({ event, matcher, handler })
    return { catch: () => undefined }
  }) as unknown as On
  const children: ReturnType<typeof fakeChild>[] = []
  const posts: {
    url: string
    socketPath?: string
    nonce?: string
    events: Record<string, unknown>[]
    release: () => void
    fail: () => void
    /** The child answers 409: the post is not this module instance's. */
    refuse: () => void
  }[] = []
  /** The engine's clock (`$.clock.now`), moved by the test. */
  let clockNow = 1_000_000
  /** While held (`holdClock`), `$.clock.now` waits. */
  let clockGate: Promise<void> = Promise.resolve()
  /** The mod's polls on the child (GET /requests/…), each held until the test answers it. */
  const polls: { url: string; socketPath?: string; respond: (status: number, body?: unknown) => void; fail: () => void }[] = []
  const timers: { kind: 'after' | 'every'; ms: number; fn: () => void; cancelled: boolean }[] = []
  const logs: string[] = []
  /** What the control ops asked of the engine, in order. */
  const calls: { op: string; args: unknown }[] = []
  const compactions: { args: unknown; finish: (outcome: Record<string, unknown>) => void; fail: (error: Error) => void }[] = []
  /** Appends held by `holdAppend`, each released by the test. */
  const appends: (() => void)[] = []
  /** Files `$.fs.read` reads (the session's transcripts). */
  const files: Record<string, string> = {}
  /** Each loop's rows on disk, as the child's GET /rows reads them; and the reads made. */
  const disk: Record<string, string[]> = {}
  const rowReads: { loop: string | null; after: string | null; socketPath?: string }[] = []
  let session = SID
  const $ = {
    plugin: { name: 'doperpowers', root: '/plug' },
    env: { get: async (name: string) => options.env?.[name] },
    session: {
      id: async () => session,
      model: async () => 'claude-haiku',
      version: async () => ({ version: '2.1.300' }),
      messages: async () => options.messages ?? [],
      usage: async () => ({ startedAt: 0, context: { tokens: 5000, window: 200000, percent: 2 }, rateLimits: [] }),
      append: (args: unknown) => {
        calls.push({ op: 'append', args })
        const denied = options.denyAppend !== undefined && JSON.stringify(args).includes(options.denyAppend)
        const stored = denied ? { deny: 'refused by a hook' } : { uuid: `row-${calls.length}`, message: {} }
        if (!options.holdAppend) {
          return Promise.resolve(stored)
        }
        return new Promise((resolve) => appends.push(() => resolve(stored)))
      },
      compact: (args: unknown) => {
        calls.push({ op: 'compact', args })
        return new Promise((resolve, reject) => compactions.push({ args, finish: resolve, fail: reject }))
      },
    },
    turn: {
      abort: async (args: unknown) => {
        calls.push({ op: 'abort', args })
      },
    },
    tool: {
      call: async (args: Record<string, unknown>) => {
        calls.push({ op: 'tool', args })
        if (options.taskStopFails?.includes(String(args.task_id))) {
          return { text: `No task found with ID: ${String(args.task_id)}`, isError: true }
        }
        return { text: `Successfully stopped task: ${String(args.task_id)}` }
      },
    },
    prompt: {
      submit: async (args: unknown) => {
        calls.push({ op: 'submit', args })
        return { text: '' }
      },
    },
    process: {
      spawn: (request: { argv: readonly string[] }) => {
        const child = fakeChild(request.argv)
        children.push(child)
        return child
      },
    },
    http: {
      fetch: (url: string, init: { socketPath?: string; body?: string; headers?: Record<string, string> }) =>
        new Promise((resolve, reject) => {
          if (url.includes('/requests/')) {
            const respond = (status: number, body?: unknown) =>
              resolve({ status, ok: status < 300, headers: {}, text: body === undefined ? '' : JSON.stringify(body) })
            polls.push({ url, socketPath: init.socketPath, respond, fail: () => reject(new Error('refused')) })
            return
          }
          if (url.startsWith('http://bridge/rows?')) {
            const q: Record<string, string> = Object.fromEntries(url.slice(url.indexOf('?') + 1).split('&').map((kv) => kv.split('=').map(decodeURIComponent)))
            rowReads.push({ loop: q.loop ?? null, after: q.after ?? null, socketPath: init.socketPath })
            const rows = disk[q.loop ?? ''] ?? []
            const at = rows.indexOf(q.after ?? '')
            resolve(at === -1 ? { status: 404, ok: false, headers: {}, text: '{"error":"not on disk"}' } : { status: 200, ok: true, headers: {}, text: JSON.stringify({ rows: rows.slice(at + 1) }) })
            return
          }
          const release = () => resolve({ status: 204, ok: true, headers: {}, text: '' })
          const fail = () => reject(new Error('refused'))
          const refuse = () => resolve({ status: 409, ok: false, headers: {}, text: '{"error":"another module\'s"}' })
          const n = posts.length
          posts.push({ url, socketPath: init.socketPath, nonce: init.headers?.['x-bridge-nonce'], events: JSON.parse(init.body ?? '[]'), release, fail, refuse })
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
      sleep: async () => undefined,
      now: async () => {
        await clockGate
        return clockNow
      },
    },
    ui: { log: (text: string) => logs.push(text) },
    fs: {
      read: async (path: string) => {
        if (files[path] === undefined) {
          throw new Error(`ENOENT: ${path}`)
        }
        return files[path]
      },
    },
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
  /** The child sends a command line; the mod's answer, once it is posted. */
  const command = async (body: Record<string, unknown>, child = 0) => {
    const id = `c${Math.random().toString(16).slice(2)}`
    children[child]!.write(line({ id, ...body }))
    for (let i = 0; i < 20; i++) {
      await settle()
      const found = events().find((e) => e.type === 'result' && e.id === id)
      if (found !== undefined) {
        return found
      }
    }
    throw new Error(`no answer to ${JSON.stringify(body)}`)
  }
  const turn = async (turnId: string, agentId?: string) =>
    hook('turn.start', { turnId })(engine, { turnId, text: 'go', ...(agentId !== undefined && { agentId }) }, async () => ({ turnId }))
  const complete = async (turnId: string, reason = 'answer', agentId?: string) => {
    await hook('turn.complete', { turnId })(engine, { turnId, answer: '', durationMs: 1, reason, ...(agentId !== undefined && { agentId }) }, async () => ({ text: '' }))
    await settle()
  }
  /** The engine's permission check for a call, answered `decision` beneath (ask: the dialog). */
  const check = async (toolUseId: string, tool: string, input: unknown, agentId?: string, decision = 'ask') =>
    hook('tool.check', { tool })(engine, { tool, input, tool_use_id: toolUseId, ...(agentId !== undefined && { agentId }) }, async () => ({ decision }))
  /** The classic PermissionRequest hooks for a call; the settings hooks beneath answer `beneath`. */
  const permission = (tool: string, input: unknown, agentId?: string, beneath: Record<string, unknown> = {}) =>
    hook('classic.PermissionRequest', { hook_event_name: 'PermissionRequest' })(
      engine,
      { hook_event_name: 'PermissionRequest', tool_name: tool, tool_input: input, session_id: SID, transcript_path: '/t', cwd: '/w', ...(agentId !== undefined && { agent_id: agentId }) },
      Object.assign(async () => beneath, { signal: new AbortController().signal }),
    ) as Promise<Record<string, unknown>>
  let rows = 0
  /** A row the session keeps, through the session.append hooks. */
  const append = async (
    door: string,
    message: Record<string, unknown>,
    extra: { uuid?: string; agentId?: string; origin?: Record<string, unknown>; next?: (inner: Record<string, unknown>) => Promise<unknown> } = {},
  ) => {
    const e = { door, message, uuid: extra.uuid ?? `u${++rows}`, origin: extra.origin ?? { kind: 'engine' }, ...(extra.agentId !== undefined && { agentId: extra.agentId }) }
    await hook('session.append', { door })(engine, e, extra.next ?? (async (inner: Record<string, unknown>) => ({ message: inner.message, uuid: inner.uuid })))
    await settle()
  }
  /** A model response row holding one block. */
  const responseRow = (block: Record<string, unknown>, extra: { uuid?: string; agentId?: string } = {}) =>
    append('response', { type: 'assistant', role: 'assistant', content: [block] }, { ...extra, origin: { kind: 'model', model: 'm' } })
  /** The hook's decision recorded beside a call's result, as the engine keeps it when it used a hook's answer. */
  const decisionMark = (agentId?: string) =>
    append('hook-context', { type: 'attachment', name: 'hook_permission_decision', role: 'user', content: [] }, { agentId, origin: { kind: 'hook', event: 'PermissionRequest' } })
  /** A call's result row. */
  const resultRow = (toolUseId: string, content: string, isError = false, agentId?: string, uuid?: string) =>
    append('tool-result', { type: 'user', role: 'user', content: [{ type: 'tool_result', tool_use_id: toolUseId, content, ...(isError && { is_error: true }) }] }, { agentId, uuid, origin: { kind: 'tool', tool: 'Bash' } })
  /** The engine's record of a call's permission decision (its `tool_decision` collector record), through the telemetry.log hooks. */
  const recorded = async (toolUseId: string, source: string, decision: 'accept' | 'reject' = 'accept', tool = 'Bash') => {
    const e = { to: 'collector', event: 'tool_decision', attributes: { decision, source, tool_name: tool, tool_use_id: toolUseId }, loggedAt: '2026-10-15T00:00:00.000Z' }
    await hook('telemetry.log', { to: 'collector' })(engine, e, async () => ({ value: undefined }))
    await settle()
  }
  let polled = 0
  /** The next poll the mod makes on the child. */
  const nextPoll = async () => {
    for (let i = 0; i < 50; i++) {
      await settle()
      const p = polls[polled]
      if (p !== undefined) {
        polled++
        return p
      }
    }
    throw new Error('no poll')
  }
  /** Fires every pending `after` timer of `ms`. */
  const fire = async (ms: number) => {
    for (const t of timers.filter((t) => t.kind === 'after' && t.ms === ms && !t.cancelled)) {
      t.cancelled = true
      t.fn()
    }
    await settle()
  }
  return {
    now: () => clockNow,
    advance: (ms: number) => (clockNow += ms),
    /** Holds `$.clock.now` until the returned function is called. */
    holdClock: () => {
      let release: () => void = () => undefined
      clockGate = new Promise((resolve) => (release = resolve))
      return release
    },
    check,
    permission,
    append,
    responseRow,
    decisionMark,
    resultRow,
    recorded,
    files,
    disk,
    rowReads,
    polls,
    nextPoll,
    fire,
    engine,
    hook,
    children,
    calls,
    compactions,
    appends,
    command,
    turn,
    complete,
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

  test("every post carries the nonce of the child's hello; a restarted child's posts carry its own", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.settle()
    expect(h.posts.length).toBeGreaterThan(1)
    expect(h.posts.every((p) => p.nonce === NONCE)).toBe(true)
    const before = h.posts.length
    h.children[0]!.end()
    await h.settle()
    h.timers.find((t) => t.kind === 'after')!.fn()
    await h.settle()
    h.children[1]!.write(hello(SID, SOCK, undefined, 'n1'))
    await h.settle()
    expect(h.posts.slice(before).map((p) => p.nonce)).toEqual(['n1'])
    expect(h.posts[before]!.events.map((e) => e.type)).toEqual(['session', 'resync'])
  })

  test('a post refused as another module instance\'s (409, a reload took the session) stops this one for good', async () => {
    const h = harness({ hold: true })
    await h.ready()
    h.posts[0]!.refuse()
    await h.settle()
    await h.turn('t1')
    for (const t of h.timers) {
      if (!t.cancelled) {
        t.fn()
      }
    }
    await h.settle()
    // Nothing more is posted, resync included; no heartbeat; no child respawned or started.
    expect(h.posts.length).toBe(1)
    expect(h.timers.find((t) => t.kind === 'every')!.cancelled).toBe(true)
    expect(h.children.length).toBe(1)
    expect(h.children[0]!.killed).toBe(true)
  })

  test("a 409 under a nonce the module has since replaced (its own child restarted) is a lost post: the new child's posts go on", async () => {
    const h = harness({ hold: true })
    await h.ready()
    h.children[0]!.end()
    await h.settle()
    h.timers.find((t) => t.kind === 'after')!.fn()
    await h.settle()
    h.children[1]!.write(hello(SID, SOCK, undefined, 'n1'))
    await h.settle()
    h.posts[0]!.refuse()
    await h.settle()
    h.timers.filter((t) => t.kind === 'after' && !t.cancelled).at(-1)!.fn()
    await h.settle()
    expect(h.posts.length).toBe(2)
    expect(h.posts[1]!.nonce).toBe('n1')
    expect(h.posts[1]!.events.map((e) => e.type)).toEqual(['session', 'resync'])
  })

  test("the first post lost (session start and all): the recovery's resync carries the session's start info, which the child takes", async () => {
    const h = harness({ failAt: [0] })
    await h.ready()
    expect(h.posts[0]!.events.map((e) => e.type)).toEqual(['session', 'resync'])
    await h.fire(500)
    expect(h.posts[1]!.events.map((e) => e.type)).toEqual(['gap', 'resync'])
    expect(h.posts[1]!.events[1]).toMatchObject({ sessionInfo: { session: SID, cwd: '/w', surface: 'terminal', isInteractive: true, model: 'claude-haiku', version: '2.1.300' } })
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
    // No row came for its blocks: the step's end waits for them, at most this long.
    await h.fire(STEP_END_WAIT_MS)
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
    expect(resent[1]).toMatchObject({ type: 'resync', streaming: [{ ...tag, upTo: 1, blocks: [{ index: 0, kind: 'text', text: 'AB', upTo: 1 }] }] })
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
        expect(first[1]).toMatchObject({
          streaming: [
            { turnId: 't0', agentId: null, step: 0, upTo: -1, blocks: [] },
            { turnId: 't1', agentId: 'a1', step: 0, upTo: 0, blocks: [{ index: 0, kind: 'text', text: 'Hel', upTo: 0 }] },
          ],
        })
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

describe('steer', () => {
  test('mid-turn: a user row appended to the conversation, mirrored in the transcript, its uuid answered', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const r = await h.command({ op: 'steer', text: 'also print the date' })
    expect(r).toMatchObject({ op: 'steer', ok: true, result: { row: 'row-1' } })
    expect(h.calls[0]).toEqual({ op: 'append', args: { message: { type: 'user', content: [{ type: 'text', text: 'also print the date' }] } } })
    expect(h.logs).toContain('steer: also print the date')
  })

  test('idle: refused, nothing appended (a send is how an idle session is reached)', async () => {
    const h = harness()
    await h.ready()
    const r = await h.command({ op: 'steer', text: 'hello' })
    expect(r).toMatchObject({ ok: false })
    expect(String(r.error)).toContain('no turn is running')
    expect(h.calls.length).toBe(0)
  })

  test('a steer that arrives during the final response wakes the session once at the turn end, without repeating its text', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    // The final response streams; the steer is appended during it; the response ends the turn.
    await h.step({ turnId: 't1', index: 2, model: 'm', messageCount: 5 }, [{ kind: 'text', index: 0, text: 'Done.' }], async () => {
      await h.command({ op: 'steer', text: 'use tabs' })
    })
    await h.complete('t1')
    const submits = h.calls.filter((c) => c.op === 'submit').map((c) => c.args as { text: string; asUser?: boolean })
    expect(submits.length).toBe(1)
    expect(submits[0]!.asUser).toBe(true)
    expect(submits[0]!.text).not.toContain('use tabs')
    expect(submits[0]!.text).toBe(STEER_WAKE)
    // The next turn's end owes nothing.
    await h.turn('t2')
    await h.complete('t2')
    expect(h.calls.filter((c) => c.op === 'submit').length).toBe(1)
  })

  test("a steer whose append is still pending when its turn ends is bound to that turn: it wakes once the row is in, and no later turn's end", async () => {
    const h = harness({ holdAppend: true })
    await h.ready()
    await h.turn('t1')
    h.children[0]!.write(line({ id: 'late', op: 'steer', text: 'mind the tests' }))
    await h.settle()
    expect(h.appends.length).toBe(1)
    await h.complete('t1') // the turn ends while the append is pending
    expect(h.calls.filter((c) => c.op === 'submit').length).toBe(0)
    await h.turn('t2') // an unrelated turn starts before the append lands
    h.appends[0]!()
    await h.settle()
    expect(h.ofType('result').find((e) => e.id === 'late')).toMatchObject({ ok: true, result: { row: 'row-1' } })
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([STEER_WAKE])
    await h.complete('t2')
    expect(h.calls.filter((c) => c.op === 'submit').length).toBe(1)
  })

  test('two steers pending when their turn answers wake it once, after both rows are in', async () => {
    const h = harness({ holdAppend: true })
    await h.ready()
    await h.turn('t1')
    h.children[0]!.write(line({ id: 's1', op: 'steer', text: 'one' }))
    h.children[0]!.write(line({ id: 's2', op: 'steer', text: 'two' }))
    await h.settle()
    expect(h.appends.length).toBe(2)
    await h.complete('t1')
    h.appends[0]!()
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'submit').length).toBe(0) // the second is still outstanding
    h.appends[1]!()
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([STEER_WAKE])
  })

  test('an appended unread steer and a pending one on one answered turn wake it once, when the pending one lands', async () => {
    const h = harness({ holdAppend: true })
    await h.ready()
    await h.turn('t1')
    h.children[0]!.write(line({ id: 's1', op: 'steer', text: 'one' }))
    await h.settle()
    h.appends[0]!() // in, and no request reads it
    await h.settle()
    h.children[0]!.write(line({ id: 's2', op: 'steer', text: 'two' }))
    await h.settle()
    await h.complete('t1')
    expect(h.calls.filter((c) => c.op === 'submit').length).toBe(0) // waits for the outstanding append
    h.appends[1]!()
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([STEER_WAKE])
    await h.turn('t2')
    await h.complete('t2')
    expect(h.calls.filter((c) => c.op === 'submit').length).toBe(1)
  })

  test("a refused append settles its turn's wake: the other steer's row still wakes it once", async () => {
    const h = harness({ holdAppend: true, denyAppend: 'blocked' })
    await h.ready()
    await h.turn('t1')
    h.children[0]!.write(line({ id: 's1', op: 'steer', text: 'kept' }))
    h.children[0]!.write(line({ id: 's2', op: 'steer', text: 'blocked' }))
    await h.settle()
    h.appends[0]!()
    await h.settle()
    await h.complete('t1')
    expect(h.calls.filter((c) => c.op === 'submit').length).toBe(0)
    h.appends[1]!() // refused
    await h.settle()
    expect(h.ofType('result').find((e) => e.id === 's2')).toMatchObject({ ok: false })
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([STEER_WAKE])
  })

  test('a pending steer whose turn is interrupted wakes nothing when its row lands', async () => {
    const h = harness({ holdAppend: true })
    await h.ready()
    await h.turn('t1')
    h.children[0]!.write(line({ id: 'late', op: 'steer', text: 'stop that' }))
    await h.settle()
    await h.complete('t1', 'aborted')
    h.appends[0]!()
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'submit').length).toBe(0)
  })

  test('a steer a later request read is not submitted again; nor one whose turn was interrupted', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'steer', text: 'read me' })
    await h.step({ turnId: 't1', index: 1, model: 'm', messageCount: 3 }, [])
    await h.complete('t1')
    await h.turn('t2')
    await h.command({ op: 'steer', text: 'too late' })
    await h.complete('t2', 'aborted')
    expect(h.calls.filter((c) => c.op === 'submit')).toEqual([])
  })
})

describe('interrupt', () => {
  test('aborts the main turn, then stops each Bash call the abort moved to the background, as Esc would', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    // An earlier Bash the model itself ran in the background: done before the interrupt.
    await h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: 'tu0', command: 'srv &' }, async () => ({ text: 'Command running in background with ID: early01. Output is being written to: /x' }))
    let finish: (text: string) => void = () => undefined
    const running = h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: 'tu1', command: 'python3 -c sleep' }, () => new Promise((resolve) => (finish = (text) => resolve({ text }))))
    await h.settle()
    const answered = h.command({ op: 'interrupt' })
    await h.settle()
    expect(h.calls[0]).toEqual({ op: 'abort', args: { turnId: 't1' } })
    finish('Command running in background with ID: b5y6zo7fe. Output is being written to: /tmp/o')
    await running
    const r = await answered
    expect(r).toMatchObject({ ok: true, result: { turnId: 't1', stopped: ['b5y6zo7fe'], running: [] } })
    expect(h.calls.filter((c) => c.op === 'tool')).toEqual([{ op: 'tool', args: { tool: 'TaskStop', task_id: 'b5y6zo7fe' } }])
  })

  test('idle: nothing to interrupt, said so', async () => {
    const h = harness()
    await h.ready()
    const r = await h.command({ op: 'interrupt' })
    expect(r).toMatchObject({ ok: true, result: { turnId: null, stopped: [], running: [] } })
    expect(h.calls.length).toBe(0)
  })

  test("only the aborted turn's calls: a background subagent's own background Bash in the same window is left running; a foreground subagent's is stopped", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const spawn = async (agentId: string, background: boolean) => {
      const e = { tool_use_id: `tu-${agentId}`, prompt: 'p', description: agentId, subagentType: 'general-purpose', background, fork: false, parentModel: 'm', provider: { plugin: 'engine', tier: 'core' } }
      await h.hook('agent.spawn', e)(h.engine, e, async () => ({ model: 'm', agentId }))
    }
    await spawn('bgagent', true)
    await spawn('fgagent', false)
    const finishers: Record<string, (text: string) => void> = {}
    const run = (id: string, agentId?: string) =>
      h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: id, command: 'sleep', ...(agentId !== undefined && { agentId }) }, () => new Promise((resolve) => (finishers[id] = (text) => resolve({ text }))))
    const calls = [run('tu-main'), run('tu-bg', 'bgagent'), run('tu-fg', 'fgagent')]
    await h.settle()
    const answered = h.command({ op: 'interrupt' })
    await h.settle()
    finishers['tu-main']!('Command running in background with ID: mainbash. Output is being written to: /o')
    // The background subagent launches its own background Bash in the window: the same words.
    finishers['tu-bg']!('Command running in background with ID: subbash. Output is being written to: /o')
    finishers['tu-fg']!('Command running in background with ID: fgbash. Output is being written to: /o')
    await Promise.all(calls)
    const r = await answered
    expect(r).toMatchObject({ ok: true, result: { turnId: 't1', stopped: ['mainbash', 'fgbash'], running: [] } })
    expect(h.calls.filter((c) => c.op === 'tool').map((c) => (c.args as { task_id: string }).task_id)).toEqual(['mainbash', 'fgbash'])
  })

  test('a TaskStop that fails is no success: the answer names the task still running', async () => {
    const h = harness({ taskStopFails: ['stuck01'] })
    await h.ready()
    await h.turn('t1')
    let finish: (text: string) => void = () => undefined
    const running = h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: 'tu1', command: 'sleep' }, () => new Promise((resolve) => (finish = (text) => resolve({ text }))))
    await h.settle()
    const answered = h.command({ op: 'interrupt' })
    await h.settle()
    finish('Command running in background with ID: stuck01. Output is being written to: /o')
    await running
    expect(await answered).toMatchObject({ ok: true, result: { turnId: 't1', stopped: [], running: ['stuck01'] } })
  })
})

/** Runs one turn.step hook with an empty response, recording the input the hook passed down. */
async function stepThrough(h: ReturnType<typeof harness>, e: Record<string, unknown>, seen: Record<string, unknown>[]) {
  const gen = h.hook('turn.step', e)(h.engine, e, (input: Record<string, unknown>) => {
    seen.push(input)
    const g = (async function* () {
      return { turnId: e.turnId, index: e.index, stopReason: 'end_turn', usage: null }
    })() as AsyncGenerator<unknown, unknown> & { result: Promise<unknown> }
    g.result = Promise.resolve({ turnId: e.turnId, index: e.index, stopReason: 'end_turn', usage: null })
    return g
  }) as AsyncGenerator<unknown, unknown>
  while (!(await gen.next()).done) {
    // drained
  }
  await h.settle()
}

describe('model and effort', () => {
  test("rewritten on each of the main loop's requests, not a subagent's; reported in the step and as an event", async () => {
    const h = harness()
    await h.ready()
    const r = await h.command({ op: 'model', model: 'claude-sonnet-5-5', effort: 'high' })
    expect(r).toMatchObject({ ok: true, result: { model: 'claude-sonnet-5-5', effort: 'high' } })
    expect(h.ofType('model')[0]).toMatchObject({ model: 'claude-sonnet-5-5', effort: 'high' })
    const seen: Record<string, unknown>[] = []
    await stepThrough(h, { turnId: 't1', index: 0, model: 'claude-haiku', effort: 'low', messageCount: 1 }, seen)
    await stepThrough(h, { turnId: 't2', index: 0, model: 'claude-haiku', messageCount: 1, agentId: 'a1' }, seen)
    expect(seen[0]).toMatchObject({ model: 'claude-sonnet-5-5', effort: 'high' })
    expect(seen[1]).toMatchObject({ model: 'claude-haiku', agentId: 'a1' })
    expect(seen[1]!.effort).toBeUndefined()
    expect(h.ofType('step').filter((e) => e.phase === 'start')[0]).toMatchObject({ model: 'claude-sonnet-5-5', effort: 'high' })
  })

  test("a family alias is resolved as the engine resolves it first, through the session's ANTHROPIC_DEFAULT_<FAMILY>_MODEL; one it does not map is refused", async () => {
    // A rewrite names the model sent on the wire: the engine resolves no alias there.
    const h = harness({ env: { ANTHROPIC_DEFAULT_SONNET_MODEL: 'claude-sonnet-5-5[1m]' } })
    await h.ready()
    expect(await h.command({ op: 'model', model: 'sonnet' })).toMatchObject({ ok: true, result: { model: 'claude-sonnet-5-5[1m]', effort: null } })
    const refused = await h.command({ op: 'model', model: 'opus' })
    expect(refused).toMatchObject({ ok: false })
    expect(String(refused.error)).toContain('ANTHROPIC_DEFAULT_OPUS_MODEL')
    expect(h.ofType('model').map((e) => e.model)).toEqual(['claude-sonnet-5-5[1m]'])
  })

  test('effort alone keeps the model; default clears both; an effort that is none is refused', async () => {
    const h = harness()
    await h.ready()
    expect(await h.command({ op: 'model', model: null, effort: 'max' })).toMatchObject({ ok: true, result: { model: null, effort: 'max' } })
    expect(await h.command({ op: 'model', model: 'default' })).toMatchObject({ ok: true, result: { model: null, effort: null } })
    const bad = await h.command({ op: 'model', model: 'claude-sonnet-5-5', effort: 'turbo' })
    expect(bad).toMatchObject({ ok: false })
    expect(String(bad.error)).toContain('effort')
  })

  test("a fresh module takes the choice and the delivered keys from the child's hello; every resync carries them", async () => {
    const h = harness()
    await h.start()
    h.children[0]!.write(hello(SID, SOCK, { override: { model: 'sonnet', effort: null }, delivered: { 'm/a': 4 } }))
    await h.settle()
    expect(h.ofType('resync')[0]).toMatchObject({ override: { model: 'sonnet', effort: null }, delivered: { 'm/a': 4 } })
    expect(await h.command({ op: 'deliver', key: { writer: 'm/a', seq: 4 }, text: 'x' })).toMatchObject({ ok: true, result: { duplicate: true } })
    const seen: Record<string, unknown>[] = []
    await stepThrough(h, { turnId: 't1', index: 0, model: 'claude-haiku', messageCount: 1 }, seen)
    expect(seen[0]).toMatchObject({ model: 'sonnet' })
  })

  test("a module that already holds its choice keeps it over a new child's hello, and hands it to that child", async () => {
    const h = harness()
    await h.ready()
    await h.command({ op: 'model', model: 'claude-opus-5-5' })
    h.children[0]!.end()
    await h.settle()
    h.timers.filter((t) => t.kind === 'after').at(-1)!.fn()
    await h.settle()
    h.children[1]!.write(hello(SID, SOCK, { override: null, delivered: {} }))
    await h.settle()
    expect(h.ofType('resync').at(-1)).toMatchObject({ override: { model: 'claude-opus-5-5', effort: null } })
  })
})

describe('a module reloaded mid-turn', () => {
  /** A module loaded into a session that already had its conversation (a reload, a resume): it saw no turn.start. */
  const RELOADED = { messages: [{ role: 'user', text: 'earlier' }] }
  const UNKNOWN = 'turn state unknown since the bridge reloaded; retry after the next model request'
  const RECORD = '/cfg/sessions/4242.json'
  /** The child's hello, naming the session record it reads (the engine's `<config>/sessions/<pid>.json`). */
  const helloWithRecord = () => line({ op: 'hello', session: SID, pid: 7, socket: SOCK, protocol: 1, nonce: NONCE, presence: RECORD })

  test('until the turn state is known, interrupt, steer and compact refuse, saying why; nothing is aborted, appended or compacted', async () => {
    const h = harness(RELOADED)
    await h.start()
    h.children[0]!.write(helloWithRecord())
    await h.settle()
    for (const body of [{ op: 'interrupt' }, { op: 'steer', text: 'and the date' }, { op: 'compact' }]) {
      expect(await h.command(body)).toMatchObject({ ok: false, error: UNKNOWN })
    }
    expect(h.calls).toEqual([])
    expect((await h.command({ op: 'ping' })).result).toMatchObject({ state: { mainTurn: null, isTurnUnknown: true } })
  })

  test("the running main turn is taken from its next request: interrupt aborts it, steer is taken, compact queues until it ends; the stream gets the turn, marked recovered", async () => {
    const h = harness(RELOADED)
    await h.ready()
    await h.step({ turnId: 't-old', index: 3, model: 'm', messageCount: 9 }, [{ kind: 'text', index: 0, text: 'still going' }])
    expect(h.ofType('turn')).toEqual([expect.objectContaining({ phase: 'start', turnId: 't-old', agentId: null, text: null, recovered: true })])
    expect(await h.command({ op: 'steer', text: 'and the date' })).toMatchObject({ ok: true, result: { row: expect.any(String) } })
    const compact = await h.command({ op: 'compact' })
    expect(compact).toMatchObject({ ok: true, result: { queued: true, turnId: 't-old' } })
    const answered = h.command({ op: 'interrupt' })
    await h.settle()
    expect(h.calls.find((c) => c.op === 'abort')).toEqual({ op: 'abort', args: { turnId: 't-old' } })
    await answered
    const ending = h.complete('t-old', 'aborted')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'compact').length).toBe(1)
    h.compactions[0]!.finish({ messages: [], tokensBefore: 9, tokensAfter: 1 })
    await ending
    expect(await h.command({ op: 'interrupt' })).toMatchObject({ ok: true, result: { turnId: null } })
  })

  test("the turn's own completion ends the unknown state: idle from there", async () => {
    const h = harness(RELOADED)
    await h.ready()
    await h.complete('t-old')
    expect(await h.command({ op: 'interrupt' })).toMatchObject({ ok: true, result: { turnId: null } })
    expect(await h.command({ op: 'compact' })).toMatchObject({ ok: true, result: { started: true } })
  })

  test('the session record saying idle ends it: read when a verb asks, and at each heartbeat', async () => {
    const h = harness(RELOADED)
    h.files[RECORD] = JSON.stringify({ pid: 4242, sessionId: SID, status: 'busy' })
    await h.start()
    h.children[0]!.write(helloWithRecord())
    await h.settle()
    expect(await h.command({ op: 'interrupt' })).toMatchObject({ ok: false, error: UNKNOWN })
    // Another session's record, or one that cannot be read, says nothing.
    h.files[RECORD] = JSON.stringify({ pid: 4242, sessionId: 'someone-else', status: 'idle' })
    expect(await h.command({ op: 'interrupt' })).toMatchObject({ ok: false, error: UNKNOWN })
    h.files[RECORD] = JSON.stringify({ pid: 4242, sessionId: SID, status: 'idle' })
    expect(await h.command({ op: 'interrupt' })).toMatchObject({ ok: true, result: { turnId: null } })
    const g = harness(RELOADED)
    g.files[RECORD] = JSON.stringify({ pid: 4242, sessionId: SID, status: 'idle' })
    await g.start()
    g.children[0]!.write(helloWithRecord())
    await g.settle()
    g.timers.find((t) => t.kind === 'every')!.fn()
    await g.settle()
    expect((await g.command({ op: 'ping' })).result).toMatchObject({ state: { mainTurn: null } })
    expect(((await g.command({ op: 'ping' })).result as { state: Record<string, unknown> }).state.isTurnUnknown).toBeUndefined()
  })

  test("a subagent's request names no main turn: nothing is recovered from it", async () => {
    const h = harness(RELOADED)
    await h.ready()
    await h.step({ turnId: 'ts', index: 0, model: 'm', messageCount: 1, agentId: 'a7' }, [{ kind: 'text', index: 0, text: 'sub' }])
    expect(h.ofType('turn')).toEqual([])
    expect(await h.command({ op: 'interrupt' })).toMatchObject({ ok: false, error: UNKNOWN })
  })

  test('a session the module started with (no message at load) is known idle from the start', async () => {
    const h = harness()
    await h.ready()
    expect(await h.command({ op: 'interrupt' })).toMatchObject({ ok: true, result: { turnId: null } })
  })
})

describe('compact', () => {
  test('asked mid-turn: queued, and run once the main turn has ended', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const r = await h.command({ op: 'compact', instructions: 'keep the plan' })
    expect(r).toMatchObject({ ok: true, result: { queued: true, turnId: 't1' } })
    expect(h.calls.length).toBe(0)
    await h.complete('ts', 'answer', 'a1') // a subagent's turn ending is not the main turn's
    expect(h.calls.length).toBe(0)
    const ending = h.complete('t1')
    await h.settle()
    expect(h.calls).toEqual([{ op: 'compact', args: { instructions: 'keep the plan' } }])
    h.compactions[0]!.finish({ messages: [], tokensBefore: 900, tokensAfter: 100 })
    await ending
    expect(h.ofType('compact')).toMatchObject([
      { phase: 'start', id: r.id },
      { phase: 'end', id: r.id, tokensBefore: 900, tokensAfter: 100 },
    ])
  })

  test('asked idle: started at once; a refusal ends it with the error', async () => {
    const h = harness()
    await h.ready()
    const r = await h.command({ op: 'compact' })
    expect(r).toMatchObject({ ok: true, result: { started: true } })
    expect(h.calls).toEqual([{ op: 'compact', args: {} }])
    h.compactions[0]!.fail(new Error('a turn is running'))
    await h.settle()
    expect(h.ofType('compact').at(-1)).toMatchObject({ phase: 'end', id: r.id, error: 'a turn is running' })
  })
})

describe('deliver', () => {
  test("submits the text as the human's words, once per key: a key redelivered, or one at or below the writer's last, is a duplicate", async () => {
    const h = harness()
    await h.ready()
    const key = { writer: 'mac/human', seq: 7 }
    expect(await h.command({ op: 'deliver', key, text: '[sminos chat p e1 from human → @you]\nhi' })).toMatchObject({ ok: true, result: { submitted: true } })
    expect(await h.command({ op: 'deliver', key, text: 'again' })).toMatchObject({ ok: true, result: { duplicate: true } })
    expect(await h.command({ op: 'deliver', key, text: 'again' })).toMatchObject({ ok: true, result: { duplicate: true } })
    expect(await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 5 }, text: 'older' })).toMatchObject({ result: { duplicate: true } })
    expect(await h.command({ op: 'deliver', key: { writer: 'mac/other', seq: 5 }, text: 'other' })).toMatchObject({ result: { submitted: true } })
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => c.args)).toEqual([
      { text: '[sminos chat p e1 from human → @you]\nhi', asUser: true },
      { text: 'other', asUser: true },
    ])
    expect(h.ofType('delivered').map((e) => [e.key, e.outcome])).toEqual([
      [key, 'submitted'],
      [key, 'duplicate'],
      [key, 'duplicate'],
      [{ writer: 'mac/human', seq: 5 }, 'duplicate'],
      [{ writer: 'mac/other', seq: 5 }, 'submitted'],
    ])
  })

  test('a deliver with no key or no text is refused', async () => {
    const h = harness()
    await h.ready()
    expect(await h.command({ op: 'deliver', text: 'x' })).toMatchObject({ ok: false })
    expect(await h.command({ op: 'deliver', key: { writer: 'w', seq: 1 } })).toMatchObject({ ok: false })
    expect(h.calls.length).toBe(0)
  })
})

describe('streaming per content block', () => {
  test("each response row names its block by the row's type and the order of the step's block starts, not its own position; the resync holds only the blocks without a row", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const chunks = [
      { kind: 'thinking', index: 0, text: 'hm' },
      { kind: 'text', index: 1, text: 'Hi' },
      { kind: 'tool', index: 2, id: 'toolu_9', name: 'Bash' },
      { kind: 'input', index: 2, json: '{"c' },
    ]
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, chunks, async () => {
      await h.settle()
      await h.responseRow({ type: 'thinking', thinking: 'hm', signature: 's' }, { uuid: 'r-think' })
      // A new child mid-step gets the blocks still without a row.
      h.children[0]!.write(hello())
      await h.settle()
      expect(h.posts.at(-1)!.events[1]).toMatchObject({
        type: 'resync',
        streaming: [
          {
            turnId: 't1',
            agentId: null,
            step: 0,
            upTo: 3,
            blocks: [
              { index: 1, kind: 'text', text: 'Hi', upTo: 1 },
              { index: 2, kind: 'tool', text: '{"c', upTo: 3, id: 'toolu_9', name: 'Bash' },
            ],
            // The blocks a row settled, so a child that takes this over ignores their late chunks.
            settled: [0],
          },
        ],
      })
      // The tool's row before the text's: the tool by its call id, the text by kind.
      await h.responseRow({ type: 'tool_use', id: 'toolu_9', name: 'Bash', input: {} }, { uuid: 'r-tool' })
      await h.responseRow({ type: 'text', text: 'Hi' }, { uuid: 'r-text' })
    })
    expect(h.ofType('block-row')).toEqual([
      expect.objectContaining({ uuid: 'r-think', turnId: 't1', agentId: null, step: 0, index: 0 }),
      expect.objectContaining({ uuid: 'r-tool', turnId: 't1', agentId: null, step: 0, index: 2 }),
      expect.objectContaining({ uuid: 'r-text', turnId: 't1', agentId: null, step: 0, index: 1 }),
    ])
  })

  test("a subagent's rows are matched in its own loop", async () => {
    const h = harness()
    await h.ready()
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'main' }], async () => {
      await h.step({ turnId: 'ts', index: 3, model: 'm', messageCount: 1, agentId: 'a7' }, [{ kind: 'text', index: 0, text: 'sub' }], async () => {
        await h.responseRow({ type: 'text', text: 'sub' }, { uuid: 'r-sub', agentId: 'a7' })
      })
    })
    expect(h.ofType('block-row')).toEqual([expect.objectContaining({ uuid: 'r-sub', turnId: 'ts', agentId: 'a7', step: 3, index: 0 })])
  })

  test('a row whose block never streamed names none', async () => {
    const h = harness()
    await h.ready()
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'a' }], async () => {
      await h.responseRow({ type: 'server_tool_use', id: 'srv_1', name: 'web_search' })
      await h.responseRow({ type: 'text', text: 'a' }, { uuid: 'r-1' })
      await h.responseRow({ type: 'text', text: 'b' }, { uuid: 'r-2' })
    })
    expect(h.ofType('block-row').map((e) => e.uuid)).toEqual(['r-1'])
  })
})

describe('requests from outside: a permission prompt', () => {
  const INPUT = { command: 'rm -rf /tmp/x', description: 'clean' }
  const REFUSED = "The user doesn't want to proceed with this tool use. The tool use was rejected."
  /** A main turn running, a call the engine put to the dialog, and its PermissionRequest raised: the hook polling. */
  const raised = async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.check('toolu_1', 'Bash', INPUT)
    const answer = h.permission('Bash', INPUT)
    const poll = await h.nextPoll()
    return { h, answer, poll }
  }
  /** A raised request whose poll handed out `decision` from `by`; the hook's answer awaited. */
  const handedOut = async (decision: Record<string, unknown>, by = 'cli') => {
    const { h, answer, poll } = await raised()
    poll.respond(200, { decision, by })
    await answer
    return h
  }

  test('raised under the tool-use id the check named, before any answer; the hook long-polls the child under the fetch bound', async () => {
    const { h, poll } = await raised()
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'toolu_1', tool: 'Bash', input: INPUT, agentId: null })])
    expect(h.ofType('raised')[0]).not.toHaveProperty('deadline')
    expect(poll.url).toBe('http://bridge/requests/toolu_1/wait?ms=20000')
    expect(poll.socketPath).toBe(SOCK)
  })

  test('a held poll that ran out is renewed', async () => {
    const { h, poll } = await raised()
    poll.respond(204)
    expect((await h.nextPoll()).url).toBe('http://bridge/requests/toolu_1/wait?ms=20000')
  })

  test("a decision handed out is the hook's answer; the engine's record that a hook decided this call settles it as the decider's, at once", async () => {
    const { h, answer, poll } = await raised()
    poll.respond(200, { decision: { behavior: 'allow' }, by: 'cli' })
    expect(await answer).toEqual({ decision: { behavior: 'allow' } })
    expect(h.ofType('settled')).toEqual([])
    await h.recorded('toolu_1', 'hook')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', winner: 'other', outcome: 'allow', by: 'cli' })])
    // Once: the call's result, its end, and the turn's end settle nothing more.
    await h.resultRow('toolu_1', 'done')
    await h.fire(RECORD_WAIT_MS)
    await h.complete('t1')
    expect(h.ofType('settled').length).toBe(1)
  })

  test("a deny from the web carries its message, and the member's id as who answered", async () => {
    const { h, answer, poll } = await raised()
    poll.respond(200, { decision: { behavior: 'deny', message: 'not there' }, by: 'm-1' })
    expect(await answer).toEqual({ decision: { behavior: 'deny', message: 'not there' } })
    await h.recorded('toolu_1', 'hook', 'reject')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', winner: 'web', outcome: 'deny', by: 'm-1' })])
  })

  test("a deny without a message reads as the human's", async () => {
    const { answer, poll } = await raised()
    poll.respond(200, { decision: { behavior: 'deny' }, by: 'cli' })
    expect(await answer).toEqual({ decision: { behavior: 'deny', message: 'The human denied this request.' } })
  })

  test("the person at the dialog deciding: the terminal's, with what they chose, even with a decision handed out (it lost the race)", async () => {
    const h = await handedOut({ behavior: 'allow' })
    await h.recorded('toolu_1', 'user_temporary')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', winner: 'terminal', outcome: 'allow', by: 'terminal' })])
    const second = await handedOut({ behavior: 'deny' })
    await second.recorded('toolu_1', 'user_permanent')
    expect(second.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', winner: 'terminal', outcome: 'allow', by: 'terminal' })])
  })

  test("the terminal answering first ends the poll with no answer; its refusal is the terminal's deny", async () => {
    const { h, answer, poll } = await raised()
    poll.respond(410, { reason: 'terminal' })
    expect(await answer).toEqual({})
    expect(h.ofType('settled')).toEqual([])
    await h.recorded('toolu_1', 'user_reject', 'reject')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', winner: 'terminal', outcome: 'deny', by: 'terminal' })])
  })

  test('a turn the person interrupted at the dialog (user_abort): withdrawn', async () => {
    const { h, poll } = await raised()
    await h.recorded('toolu_1', 'user_abort', 'reject')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', winner: 'other', outcome: 'withdrawn', by: 'bridge' })])
    poll.respond(410, { reason: 'settled' })
  })

  test("a hook's decision with none of the bridge's handed out (another plugin's hook decided): withdrawn, and said so in the debug log", async () => {
    const { h, poll } = await raised()
    await h.recorded('toolu_1', 'hook')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', outcome: 'withdrawn', by: 'bridge' })])
    expect(h.logs.join('\n')).toContain('toolu_1')
    poll.respond(410, { reason: 'settled' })
  })

  test("a hook's decision other than the one handed out: withdrawn, not credited to the decider", async () => {
    const h = await handedOut({ behavior: 'allow' })
    await h.recorded('toolu_1', 'hook', 'reject')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', outcome: 'withdrawn', by: 'bridge' })])
  })

  test("records of other calls (rules, mode) settle nothing", async () => {
    const { h, poll } = await raised()
    await h.recorded('toolu_other', 'config')
    await h.recorded('toolu_other', 'hook')
    expect(h.ofType('settled')).toEqual([])
    poll.respond(410, { reason: 'settled' })
  })

  test('no record by the call\'s result: the transcript\'s mark of a hook\'s decision for this call says the decider\'s', async () => {
    const h = await handedOut({ behavior: 'allow' })
    h.files['/t'] = [
      JSON.stringify({ type: 'attachment', uuid: 'm1', attachment: { type: 'hook_permission_decision', decision: 'allow', toolUseID: 'toolu_1', hookEvent: 'PermissionRequest' } }),
      JSON.stringify({ type: 'user', uuid: 'r1', message: { content: [{ type: 'tool_result', tool_use_id: 'toolu_1', content: 'done' }] } }),
      '',
    ].join('\n')
    await h.resultRow('toolu_1', 'done', false, undefined, 'r1')
    expect(h.ofType('settled')).toEqual([])
    await h.fire(RECORD_WAIT_MS)
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', winner: 'other', outcome: 'allow', by: 'cli' })])
  })

  test("no record, and no mark for this call beside its result: the terminal's, with what the result shows; another call's mark does not count", async () => {
    const h = await handedOut({ behavior: 'allow' })
    h.files['/t'] = [
      JSON.stringify({ type: 'attachment', uuid: 'm0', attachment: { type: 'hook_permission_decision', decision: 'allow', toolUseID: 'toolu_0', hookEvent: 'PermissionRequest' } }),
      JSON.stringify({ type: 'user', uuid: 'r1', message: { content: [{ type: 'tool_result', tool_use_id: 'toolu_1', content: REFUSED, is_error: true }] } }),
    ].join('\n')
    await h.resultRow('toolu_1', REFUSED, true, undefined, 'r1')
    await h.fire(RECORD_WAIT_MS)
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', winner: 'terminal', outcome: 'deny', by: 'terminal' })])
  })

  test('no record, and the result not yet in the transcript: read again until it is; never found, withdrawn', async () => {
    const h = await handedOut({ behavior: 'allow' })
    h.files['/t'] = ''
    await h.resultRow('toolu_1', 'done', false, undefined, 'r1')
    await h.fire(RECORD_WAIT_MS)
    expect(h.ofType('settled')).toEqual([])
    h.files['/t'] = JSON.stringify({ type: 'user', uuid: 'r1', message: { content: [] } })
    await h.fire(TRANSCRIPT_RETRY_MS)
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', by: 'terminal', outcome: 'allow' })])
    const lost = await handedOut({ behavior: 'allow' })
    lost.files['/t'] = ''
    await lost.resultRow('toolu_1', 'done', false, undefined, 'r9')
    await lost.fire(RECORD_WAIT_MS)
    for (let i = 0; i < 10; i++) {
      await lost.fire(TRANSCRIPT_RETRY_MS)
    }
    expect(lost.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', outcome: 'withdrawn', by: 'bridge' })])
  })

  test('the settings hooks beneath deciding: nothing is raised, their answer stands', async () => {
    const h = harness()
    await h.ready()
    await h.check('toolu_1', 'Bash', INPUT)
    expect(await h.permission('Bash', INPUT, undefined, { decision: { behavior: 'deny', message: 'policy' } })).toEqual({ decision: { behavior: 'deny', message: 'policy' } })
    expect(h.ofType('raised')).toEqual([])
    expect(h.polls).toEqual([])
  })

  test('two identical calls, the first decided beneath: the second is raised under its own id, and answered from outside', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.check('toolu_1', 'Bash', INPUT)
    await h.permission('Bash', INPUT, undefined, { decision: { behavior: 'allow' } })
    await h.check('toolu_2', 'Bash', INPUT)
    const answer = h.permission('Bash', INPUT)
    const poll = await h.nextPoll()
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'toolu_2' })])
    expect(poll.url).toBe('http://bridge/requests/toolu_2/wait?ms=20000')
    poll.respond(200, { decision: { behavior: 'allow' }, by: 'cli' })
    await answer
    await h.recorded('toolu_2', 'hook')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_2', by: 'cli' })])
  })

  test('a call the engine decided with no dialog (its mode) leaves no check for a later identical call to take', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.check('toolu_1', 'Bash', INPUT)
    await h.recorded('toolu_1', 'config')
    await h.check('toolu_2', 'Bash', INPUT)
    void h.permission('Bash', INPUT)
    ;(await h.nextPoll()).respond(410, { reason: 'settled' })
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'toolu_2' })])
  })

  test('answered at the dialog while the settings hooks beneath still ran: nothing is raised', async () => {
    const h = harness()
    await h.ready()
    await h.check('toolu_1', 'Bash', INPUT)
    let beneath: (v: Record<string, unknown>) => void = () => undefined
    const answer = h.hook('classic.PermissionRequest', { hook_event_name: 'PermissionRequest' })(
      h.engine,
      { hook_event_name: 'PermissionRequest', tool_name: 'Bash', tool_input: INPUT, session_id: SID, transcript_path: '/t', cwd: '/w' },
      Object.assign(() => new Promise((resolve) => (beneath = resolve)), { signal: new AbortController().signal }),
    )
    await h.settle()
    await h.recorded('toolu_1', 'user_temporary')
    beneath({})
    expect(await answer).toEqual({})
    expect(h.ofType('raised')).toEqual([])
    expect(h.ofType('settled')).toEqual([])
  })

  test("answered at the dialog while the hook reads the clock, after the hooks beneath: still nothing is raised", async () => {
    const h = harness()
    await h.ready()
    await h.check('toolu_1', 'Bash', INPUT)
    const release = h.holdClock()
    const answer = h.permission('Bash', INPUT)
    await h.settle()
    await h.recorded('toolu_1', 'user_temporary')
    release()
    expect(await answer).toEqual({})
    await h.settle()
    expect(h.ofType('raised')).toEqual([])
    expect(h.polls).toEqual([])
  })

  test('a turn that ends with the request unanswered withdraws it, and the poll ends there', async () => {
    const { h, answer, poll } = await raised()
    await h.complete('t1', 'aborted')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', winner: 'other', outcome: 'withdrawn', by: 'bridge' })])
    poll.respond(410, { reason: 'settled' })
    expect(await answer).toEqual({})
  })

  test("the bridge's interrupt with the dialog open: a withdrawal, whatever the record or the result says", async () => {
    const { h, poll } = await raised()
    await h.command({ op: 'interrupt' })
    await h.recorded('toolu_1', 'user_reject', 'reject')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', outcome: 'withdrawn', by: 'bridge' })])
    poll.respond(410, { reason: 'settled' })
  })

  test('the session ending withdraws every request still pending', async () => {
    const { h, poll } = await raised()
    await h.hook('session.end')(h.engine, { reason: 'other' }, async () => ({}))
    await h.settle()
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_1', outcome: 'withdrawn', by: 'bridge' })])
    poll.respond(410, { reason: 'settled' })
  })

  test('a call no check named still raises a request, under an id of its own', async () => {
    const h = harness()
    await h.ready()
    void h.permission('Bash', INPUT)
    const poll = await h.nextPoll()
    const id = String(h.ofType('raised')[0]?.request)
    expect(id).toMatch(/^request-/)
    expect(poll.url).toBe(`http://bridge/requests/${id}/wait?ms=20000`)
    poll.respond(410, { reason: 'settled' })
  })

  test('a resync carries the pending requests and the recent settlements', async () => {
    const { h, answer, poll } = await raised()
    await h.check('toolu_2', 'Bash', { command: 'ls' })
    void h.permission('Bash', { command: 'ls' })
    const second = await h.nextPoll()
    poll.respond(410, { reason: 'terminal' })
    await answer
    await h.recorded('toolu_1', 'user_reject', 'reject')
    h.children[0]!.write(hello())
    await h.settle()
    const resync = h.posts.at(-1)!.events[1]!
    expect(resync).toMatchObject({
      type: 'resync',
      pending: [expect.objectContaining({ request: 'toolu_2', tool: 'Bash', input: { command: 'ls' }, agentId: null })],
      settled: [expect.objectContaining({ request: 'toolu_1', winner: 'terminal', outcome: 'deny', by: 'terminal' })],
    })
    second.respond(410, { reason: 'settled' })
  })
})

describe('requests from outside: subagents', () => {
  const INPUT = { command: 'make' }
  const spawn = (h: ReturnType<typeof harness>, agentId: string, background: boolean) =>
    h.hook('agent.spawn', { tool_use_id: 'tu' })(h.engine, { tool_use_id: 'tu', subagentType: 'general-purpose', description: 'd', background }, async () => ({ agentId, model: 'm' }))

  test("a background subagent's request: raised with its deadline, polled only until it, then left to the terminal, whose record settles it", async () => {
    const h = harness()
    await h.ready()
    await spawn(h, 'a9', true)
    await h.turn('ts', 'a9')
    await h.check('toolu_b', 'Bash', INPUT, 'a9')
    const answer = h.permission('Bash', INPUT, 'a9')
    const poll = await h.nextPoll()
    expect(h.ofType('raised')[0]).toMatchObject({ request: 'toolu_b', agentId: 'a9', deadline: h.now() + BACKGROUND_WINDOW_MS })
    expect(poll.url).toBe(`http://bridge/requests/toolu_b/wait?ms=${BACKGROUND_WINDOW_MS}`)
    h.advance(1_000)
    poll.respond(204)
    expect((await h.nextPoll()).url).toBe(`http://bridge/requests/toolu_b/wait?ms=${BACKGROUND_WINDOW_MS - 1_000}`)
    h.advance(BACKGROUND_WINDOW_MS)
    h.polls.at(-1)!.respond(204)
    expect(await answer).toEqual({})
    // The dialog is the terminal's now: no more polls; the engine's record says what it did.
    await h.settle()
    expect(h.polls.length).toBe(2)
    expect(h.ofType('settled')).toEqual([])
    await h.recorded('toolu_b', 'user_temporary')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_b', winner: 'terminal', outcome: 'allow', by: 'terminal' })])
  })

  test("with no record, a subagent's result is read from its own transcript", async () => {
    const h = harness()
    await h.ready()
    await spawn(h, 'a9', true)
    await h.check('toolu_b', 'Bash', INPUT, 'a9')
    const answer = h.permission('Bash', INPUT, 'a9')
    ;(await h.nextPoll()).respond(200, { decision: { behavior: 'allow' }, by: 'cli' })
    await answer
    h.files['/t/subagents/agent-a9.jsonl'] = [
      JSON.stringify({ type: 'attachment', uuid: 'm1', attachment: { type: 'hook_permission_decision', decision: 'allow', toolUseID: 'toolu_b' } }),
      JSON.stringify({ type: 'user', uuid: 'r1' }),
    ].join('\n')
    await h.resultRow('toolu_b', 'built', false, 'a9', 'r1')
    await h.fire(RECORD_WAIT_MS)
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_b', by: 'cli', outcome: 'allow' })])
  })

  test('a subagent the bridge does not know of is bounded the same way; a foreground one is not', async () => {
    const h = harness()
    await h.ready()
    await h.check('toolu_u', 'Bash', INPUT, 'a-unknown')
    void h.permission('Bash', INPUT, 'a-unknown')
    ;(await h.nextPoll()).respond(410, { reason: 'settled' })
    expect(h.ofType('raised')[0]).toHaveProperty('deadline')
    await h.turn('t1')
    await spawn(h, 'a5', false)
    await h.check('toolu_f', 'Bash', INPUT, 'a5')
    void h.permission('Bash', INPUT, 'a5')
    ;(await h.nextPoll()).respond(410, { reason: 'settled' })
    expect(h.ofType('raised')[1]).toMatchObject({ request: 'toolu_f', agentId: 'a5' })
    expect(h.ofType('raised')[1]).not.toHaveProperty('deadline')
  })
})

describe('requests from outside: questions', () => {
  const FRUIT = { question: 'Which fruit?', header: 'Fruit', multiSelect: false, options: [{ label: 'Apple', description: 'a' }, { label: 'Mango', description: 'm' }] }
  const answered = (label: string) => `Your questions have been answered: "Which fruit?"="${label}". You can now continue with these answers in mind.`
  /** The ask mod's dialog for a question, its PermissionRequest polling. */
  const asked = async (id = 'toolu_plugin_1') => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.check(id, 'AskUserQuestion', { questions: [FRUIT] })
    const answer = h.permission('AskUserQuestion', { questions: [FRUIT] })
    const poll = await h.nextPoll()
    return { h, answer, poll }
  }

  test("answered from outside: the allow carries the dialog's own questions with the answers; the record of the hook's decision settles it as answered", async () => {
    const { h, answer, poll } = await asked()
    poll.respond(200, { decision: { behavior: 'allow', updatedInput: { answers: { 'Which fruit?': 'Mango' } } }, by: 'cli' })
    expect(await answer).toEqual({ decision: { behavior: 'allow', updatedInput: { questions: [FRUIT], answers: { 'Which fruit?': 'Mango' } } } })
    await h.recorded('toolu_plugin_1', 'hook', 'accept', 'AskUserQuestion')
    onAskNote({ kind: 'dialog', toolUseId: 'toolu_plugin_1', isError: false, text: answered('Mango') })
    await h.fire(RECORD_WAIT_MS)
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_plugin_1', winner: 'other', outcome: 'answered', by: 'cli' })])
  })

  test('the same answer given in the terminal first: the terminal\'s, though the answers match', async () => {
    const { h, answer, poll } = await asked()
    poll.respond(200, { decision: { behavior: 'allow', updatedInput: { answers: { 'Which fruit?': 'Mango' } } }, by: 'cli' })
    await answer
    await h.recorded('toolu_plugin_1', 'user_temporary', 'accept', 'AskUserQuestion')
    onAskNote({ kind: 'dialog', toolUseId: 'toolu_plugin_1', isError: false, text: answered('Mango') })
    await h.settle()
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_plugin_1', winner: 'terminal', outcome: 'answered', by: 'terminal' })])
  })

  test('declined in the terminal: its deny', async () => {
    const { h, answer, poll } = await asked()
    poll.respond(410, { reason: 'terminal' })
    await answer
    await h.recorded('toolu_plugin_1', 'user_reject', 'reject', 'AskUserQuestion')
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_plugin_1', winner: 'terminal', outcome: 'deny', by: 'terminal' })])
  })

  test('a dialog that settled with no record of who decided it: withdrawn (the dialog keeps no transcript rows to read)', async () => {
    const { h, answer, poll } = await asked()
    poll.respond(200, { decision: { behavior: 'allow', updatedInput: { answers: { 'Which fruit?': 'Mango' } } }, by: 'cli' })
    await answer
    onAskNote({ kind: 'dialog', toolUseId: 'toolu_plugin_1', isError: false, text: answered('Mango') })
    await h.settle()
    expect(h.ofType('settled')).toEqual([])
    await h.fire(RECORD_WAIT_MS)
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_plugin_1', outcome: 'withdrawn', by: 'bridge' })])
  })

  test('an async question: raised as it opens, answered through the ask mod, settled as it is answered, withdrawn when forgotten', async () => {
    const h = harness()
    await h.ready()
    onAskNote({ kind: 'open', id: 'toolu_a1', questions: [FRUIT] })
    await h.settle()
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'toolu_a1', tool: ASK_TOOL, input: { questions: [FRUIT] }, agentId: null, async: true })])
    // No ask of the ask mod's: the answer is refused there, and said so.
    expect(await h.command({ op: 'answer', request: 'toolu_a1', answers: { 'Which fruit?': 'Apple' }, by: 'cli' })).toMatchObject({ ok: false })
    onAskNote({ kind: 'answered', id: 'toolu_a1', by: 'cli' })
    await h.settle()
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_a1', winner: 'other', outcome: 'answered', by: 'cli' })])
    onAskNote({ kind: 'open', id: 'toolu_a2', questions: [FRUIT] })
    onAskNote({ kind: 'forgotten', ids: ['toolu_a2'] })
    await h.settle()
    expect(h.ofType('settled').at(-1)).toMatchObject({ request: 'toolu_a2', outcome: 'withdrawn', by: 'bridge' })
    // An async question does not end with a turn.
    onAskNote({ kind: 'open', id: 'toolu_a3', questions: [FRUIT] })
    await h.turn('t9')
    await h.complete('t9')
    expect(h.ofType('settled').map((e) => e.request)).not.toContain('toolu_a3')
  })

  test("the ask mod's blocking question: raised under its dialog with the outer call's toolUseId; the dialog's own call and result are not posted", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const fromPlugin = <T extends object>(fn: T) => Object.assign(fn, { origin: { kind: 'tool', plugin: 'doperpowers' } })
    let endOuter: (v: Record<string, unknown>) => void = () => undefined
    const outer = h.hook('tool.call', { tool: ASK_TOOL })(
      h.engine,
      { tool: ASK_TOOL, tool_use_id: 'toolu_01outer', questions: [FRUIT] },
      Object.assign(() => new Promise((resolve) => (endOuter = resolve)), { origin: { kind: 'engine', plugin: 'engine' } }),
    )
    await h.settle()
    // The dialog the ask mod opens inside its call: one question, its token as the header.
    let endDialog: (v: Record<string, unknown>) => void = () => undefined
    const dialog = h.hook('tool.call', { tool: 'AskUserQuestion' })(
      h.engine,
      { tool: 'AskUserQuestion', tool_use_id: 'toolu_plugin_1', questions: [{ ...FRUIT, header: 'ask-1' }] },
      fromPlugin(() => new Promise((resolve) => (endDialog = resolve))),
    )
    await h.check('toolu_plugin_1', 'AskUserQuestion', { questions: [FRUIT] })
    const answer = h.permission('AskUserQuestion', { questions: [FRUIT] })
    const poll = await h.nextPoll()
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'toolu_plugin_1', toolUseId: 'toolu_01outer', tool: 'AskUserQuestion' })])
    poll.respond(200, { decision: { behavior: 'allow', updatedInput: { answers: { 'Which fruit?': 'Mango' } } }, by: 'm-7' })
    await answer
    endDialog({ text: answered('Mango') })
    await dialog
    endOuter({ text: answered('Mango') })
    await outer
    await h.recorded('toolu_plugin_1', 'hook', 'accept', 'AskUserQuestion')
    await h.settle()
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_plugin_1', winner: 'web', by: 'm-7' })])
    expect(h.ofType('tool').map((e) => [e.phase, e.toolUseId])).toEqual([['call', 'toolu_01outer'], ['result', 'toolu_01outer']])
  })

  test("two running asks sharing the dialog's first question: the pairing is ambiguous, so no toolUseId; the dialog's call and result still not posted", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const ends: ((v: Record<string, unknown>) => void)[] = []
    const outers = ['toolu_01a', 'toolu_01b'].map((id) =>
      h.hook('tool.call', { tool: ASK_TOOL })(
        h.engine,
        { tool: ASK_TOOL, tool_use_id: id, questions: [FRUIT] },
        Object.assign(() => new Promise((resolve) => ends.push(resolve)), { origin: { kind: 'engine', plugin: 'engine' } }),
      ),
    )
    await h.settle()
    let endDialog: (v: Record<string, unknown>) => void = () => undefined
    const dialog = h.hook('tool.call', { tool: 'AskUserQuestion' })(
      h.engine,
      { tool: 'AskUserQuestion', tool_use_id: 'toolu_plugin_2', questions: [{ ...FRUIT, header: 'ask-1' }] },
      Object.assign(() => new Promise((resolve) => (endDialog = resolve)), { origin: { kind: 'tool', plugin: 'doperpowers' } }),
    )
    await h.check('toolu_plugin_2', 'AskUserQuestion', { questions: [FRUIT] })
    void h.permission('AskUserQuestion', { questions: [FRUIT] })
    const poll = await h.nextPoll()
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'toolu_plugin_2' })])
    expect(h.ofType('raised')[0]).not.toHaveProperty('toolUseId')
    poll.respond(410, { reason: 'settled' })
    endDialog({ text: answered('Apple') })
    await dialog
    ends.forEach((end) => end({ text: answered('Apple') }))
    await Promise.all(outers)
    await h.settle()
    expect(h.ofType('tool').map((e) => e.toolUseId)).toEqual(['toolu_01a', 'toolu_01b', 'toolu_01a', 'toolu_01b'])
  })

  test('a question raised under its own call carries no toolUseId', async () => {
    const { h, poll } = await asked('toolu_01native')
    expect(h.ofType('raised')[0]).toMatchObject({ request: 'toolu_01native' })
    expect(h.ofType('raised')[0]).not.toHaveProperty('toolUseId')
    poll.respond(410, { reason: 'settled' })
  })

  test("an async question opened in the terminal, its dialog answered from outside: settled with the dialog's winner", async () => {
    const { h, answer, poll } = await asked('toolu_plugin_9')
    onAskNote({ kind: 'open', id: 'toolu_a1', questions: [FRUIT] })
    poll.respond(200, { decision: { behavior: 'allow', updatedInput: { answers: { 'Which fruit?': 'Mango' } } }, by: 'm-7' })
    await answer
    await h.recorded('toolu_plugin_9', 'hook', 'accept', 'AskUserQuestion')
    onAskNote({ kind: 'answered', id: 'toolu_a1', dialog: 'toolu_plugin_9' })
    await h.settle()
    expect(h.ofType('settled')).toEqual([
      expect.objectContaining({ request: 'toolu_plugin_9', winner: 'web', outcome: 'answered', by: 'm-7' }),
      expect.objectContaining({ request: 'toolu_a1', winner: 'web', outcome: 'answered', by: 'm-7' }),
    ])
  })

  test("an async question's dialog answered in the terminal, its note before the record: settled with the terminal once the dialog is", async () => {
    const { h, answer, poll } = await asked('toolu_plugin_9')
    onAskNote({ kind: 'open', id: 'toolu_a1', questions: [FRUIT] })
    poll.respond(410, { reason: 'terminal' })
    await answer
    onAskNote({ kind: 'answered', id: 'toolu_a1', dialog: 'toolu_plugin_9' })
    await h.settle()
    expect(h.ofType('settled')).toEqual([])
    await h.recorded('toolu_plugin_9', 'user_temporary', 'accept', 'AskUserQuestion')
    expect(h.ofType('settled')).toEqual([
      expect.objectContaining({ request: 'toolu_plugin_9', by: 'terminal' }),
      expect.objectContaining({ request: 'toolu_a1', winner: 'terminal', outcome: 'answered', by: 'terminal' }),
    ])
  })

  test("an async question's dialog answered in the terminal while its settings hooks still ran: no dialog request, and the question is the terminal's", async () => {
    const h = harness()
    await h.ready()
    onAskNote({ kind: 'open', id: 'toolu_a1', questions: [FRUIT] })
    await h.check('toolu_plugin_9', 'AskUserQuestion', { questions: [FRUIT] })
    let beneath: (v: Record<string, unknown>) => void = () => undefined
    const answer = h.hook('classic.PermissionRequest', { hook_event_name: 'PermissionRequest' })(
      h.engine,
      { hook_event_name: 'PermissionRequest', tool_name: 'AskUserQuestion', tool_input: { questions: [FRUIT] }, session_id: SID, transcript_path: '/t', cwd: '/w' },
      Object.assign(() => new Promise((resolve) => (beneath = resolve)), { signal: new AbortController().signal }),
    )
    await h.settle()
    await h.recorded('toolu_plugin_9', 'user_temporary', 'accept', 'AskUserQuestion')
    beneath({})
    expect(await answer).toEqual({})
    onAskNote({ kind: 'answered', id: 'toolu_a1', dialog: 'toolu_plugin_9' })
    await h.settle()
    expect(h.ofType('raised').map((e) => e.request)).toEqual(['toolu_a1'])
    expect(h.ofType('settled')).toEqual([expect.objectContaining({ request: 'toolu_a1', winner: 'terminal', outcome: 'answered', by: 'terminal' })])
  })
})

describe('the export to the host', () => {
  const FRUIT = { question: 'Which fruit?', header: 'Fruit', multiSelect: false, options: [{ label: 'Apple', description: 'a' }, { label: 'Mango', description: 'm' }] }
  const WAITING = 'Your questions are waiting for the human.'
  const askUse = (id: string, isAsync: boolean) => ({ type: 'tool_use', id, name: ASK_TOOL, input: { questions: [FRUIT], async: isAsync } })
  /** The ask tool's result row, as the engine keeps it. */
  const askResult = (h: ReturnType<typeof harness>, id: string, uuid: string) =>
    h.append('tool-result', { type: 'user', role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: WAITING }] }, { uuid, origin: { kind: 'tool', tool: ASK_TOOL } })

  test("a main-loop text row that may hold a mark goes to the child whole, as the transcript keeps it, keyed by the row's uuid", async () => {
    const h = harness()
    await h.ready()
    const text = 'Reading.\n<message>done with the parser</message>\nAnd `<message>a literal</message>`.'
    await h.responseRow({ type: 'text', text }, { uuid: 'r-m' })
    expect(h.ofType('export')).toEqual([
      expect.objectContaining({ type: 'export', records: [{ type: 'assistant', uuid: 'r-m', message: { content: [{ type: 'text', text }] } }] }),
    ])
  })

  test("every alias of the mark, and the form the streaming hook draws, may hold one; the child's parser decides", async () => {
    const h = harness()
    await h.ready()
    await h.responseRow({ type: 'text', text: 'note <insight>this</insight>' }, { uuid: 'r-alias' })
    await h.responseRow({ type: 'text', text: '\x1b[1;32mmessage\x1b[0m drawn' }, { uuid: 'r-drawn' })
    expect(h.ofType('export').map((e) => (e.records as { uuid: string }[])[0]!.uuid)).toEqual(['r-alias', 'r-drawn'])
  })

  test("a row with no mark, a thinking row, and a subagent's row are not exported (the Stop hook reads the main chain only)", async () => {
    const h = harness()
    await h.ready()
    await h.responseRow({ type: 'text', text: 'plain working text' })
    await h.responseRow({ type: 'thinking', thinking: '<message>thought</message>', signature: 's' })
    await h.responseRow({ type: 'text', text: '<message>from a subagent</message>' }, { agentId: 'a7' })
    expect(h.ofType('export')).toEqual([])
  })

  test("a text past the events' cap is left to the Stop hook's export, which reads it whole, and said so in the debug log", async () => {
    const h = harness()
    await h.ready()
    await h.responseRow({ type: 'text', text: `<message>${'x'.repeat(TEXT_CAP)}</message>` }, { uuid: 'r-long' })
    expect(h.ofType('export')).toEqual([])
    expect(h.logs.some((l) => l.includes('r-long'))).toBe(true)
  })

  test('an async ask goes with its result, both rows in one export, whichever row the engine keeps first', async () => {
    const h = harness()
    await h.ready()
    await h.responseRow(askUse('toolu_q1', true), { uuid: 'r-use1' })
    expect(h.ofType('export')).toEqual([])
    await askResult(h, 'toolu_q1', 'r-res1')
    await askResult(h, 'toolu_q2', 'r-res2')
    await h.responseRow(askUse('toolu_q2', true), { uuid: 'r-use2' })
    const result = (id: string, uuid: string) => ({ type: 'user', uuid, message: { content: [{ type: 'tool_result', tool_use_id: id, content: WAITING }] } })
    expect(h.ofType('export').map((e) => e.records)).toEqual([
      [{ type: 'assistant', uuid: 'r-use1', message: { content: [askUse('toolu_q1', true)] } }, result('toolu_q1', 'r-res1')],
      [{ type: 'assistant', uuid: 'r-use2', message: { content: [askUse('toolu_q2', true)] } }, result('toolu_q2', 'r-res2')],
    ])
  })

  test("a blocking ask, an async one whose result never came, and another tool's result are not exported", async () => {
    const h = harness()
    await h.ready()
    await h.responseRow(askUse('toolu_b', false), { uuid: 'r-b' })
    await askResult(h, 'toolu_b', 'r-bres')
    await h.responseRow(askUse('toolu_open', true), { uuid: 'r-open' })
    await h.resultRow('toolu_bash', 'a Bash result')
    expect(h.ofType('export')).toEqual([])
  })
})

describe('row notices and the cut', () => {
  const notices = (h: ReturnType<typeof harness>) =>
    h.events().filter((e) => e.type === 'block-row' || e.type === 'row-seen').map((e) => `${String(e.type)}:${String(e.uuid)}`)

  test("every row is noticed once it is written (its append resolved), once: a response row by its block-row, any other by row-seen, with its loop and door", async () => {
    const h = harness()
    await h.ready()
    let posted: string[] = []
    const next = async (inner: Record<string, unknown>) => {
      await h.settle()
      posted = notices(h)
      return { message: inner.message, uuid: inner.uuid }
    }
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'Hi' }], async () => {
      await h.append('response', { type: 'assistant', role: 'assistant', content: [{ type: 'text', text: 'Hi' }] }, { uuid: 'r-text', origin: { kind: 'model', model: 'm' }, next })
      expect(posted).toEqual([])
      expect(notices(h)).toEqual(['block-row:r-text'])
    })
    await h.append('tool-result', { type: 'user', role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_1', content: 'ok' }] }, { uuid: 'r-res', next })
    expect(posted).toEqual(['block-row:r-text'])
    await h.append('attachment', { type: 'attachment', name: 'nested_memory', role: 'user', content: [] }, { uuid: 'r-att', agentId: 'a7' })
    await h.append('prompt', { type: 'user', role: 'user', content: [{ type: 'text', text: 'go' }] }, { uuid: 'r-prompt' })
    expect(notices(h)).toEqual(['block-row:r-text', 'row-seen:r-res', 'row-seen:r-att', 'row-seen:r-prompt'])
    expect(h.ofType('row-seen')).toEqual([
      expect.objectContaining({ uuid: 'r-res', agentId: null, door: 'tool-result' }),
      expect.objectContaining({ uuid: 'r-att', agentId: 'a7', door: 'attachment' }),
      expect.objectContaining({ uuid: 'r-prompt', agentId: null, door: 'prompt' }),
    ])
  })

  test("notice order is write order: an append the engine began first but wrote second is noticed second (2.1.300: a session's first prompt, written after the attachments announced after it)", async () => {
    const h = harness()
    await h.ready()
    let writePrompt: () => void = () => undefined
    const prompt = h.append('prompt', { type: 'user', role: 'user', content: [{ type: 'text', text: 'go' }] }, {
      uuid: 'r-prompt',
      next: (inner) => new Promise((resolve) => (writePrompt = () => resolve({ message: inner.message, uuid: inner.uuid }))),
    })
    await h.append('attachment', { type: 'attachment', name: 'environment', role: 'user', content: [] }, { uuid: 'r-env' })
    writePrompt()
    await prompt
    await h.settle()
    expect(notices(h)).toEqual(['row-seen:r-env', 'row-seen:r-prompt'])
  })

  test("a step's end follows every block-row of its step: one the engine appends after the request's result (a refusal or truncation row it withheld) holds the end until it is named", async () => {
    const h = harness()
    await h.ready()
    const order = () => h.events().filter((e) => e.type === 'block-row' || (e.type === 'step' && e.phase === 'end')).map((e) => `${String(e.type)}:${String(e.step)}`)
    // The usual path: the row is appended while the request streams.
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'a' }], async () => {
      await h.responseRow({ type: 'text', text: 'a' }, { uuid: 'r-a' })
    })
    expect(order()).toEqual(['block-row:0', 'step:0'])
    // A row withheld until the stream is done.
    await h.step({ turnId: 't1', index: 1, model: 'm', messageCount: 3 }, [{ kind: 'text', index: 0, text: 'b' }, { kind: 'tool', index: 1, id: 'toolu_1', name: 'Bash' }], async () => {
      await h.responseRow({ type: 'text', text: 'b' }, { uuid: 'r-b' })
    })
    expect(order()).toEqual(['block-row:0', 'step:0', 'block-row:1'])
    await h.responseRow({ type: 'tool_use', id: 'toolu_1', name: 'Bash', input: {} }, { uuid: 'r-tool' })
    expect(order()).toEqual(['block-row:0', 'step:0', 'block-row:1', 'block-row:1', 'step:1'])
  })

  test("a step's held end goes out after STEP_END_WAIT_MS with a block whose row never came, or before the loop's next request, whichever is first", async () => {
    const h = harness()
    await h.ready()
    const ends = () => h.ofType('step').map((e) => `${String(e.phase)}:${String(e.step)}`)
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'cut short' }])
    expect(ends()).toEqual(['start:0'])
    await h.fire(STEP_END_WAIT_MS)
    expect(ends()).toEqual(['start:0', 'end:0'])
    // Its block, with no row, is in no later resync.
    h.children[0]!.end()
    await h.settle()
    h.timers.find((t) => t.kind === 'after' && t.ms === 1000 && !t.cancelled)!.fn()
    await h.settle()
    h.children[1]!.write(hello(SID, SOCK, undefined, 'n1'))
    await h.settle()
    expect(h.ofType('resync').at(-1)!.streaming).toEqual([])
    await h.step({ turnId: 't1', index: 1, model: 'm', messageCount: 3 }, [{ kind: 'text', index: 0, text: 'again' }])
    await h.step({ turnId: 't1', index: 2, model: 'm', messageCount: 5 }, [])
    expect(ends()).toEqual(['start:0', 'end:0', 'start:1', 'end:1', 'start:2', 'end:2'])
    await h.fire(STEP_END_WAIT_MS)
    expect(ends()).toEqual(['start:0', 'end:0', 'start:1', 'end:1', 'start:2', 'end:2'])
  })

  test("once a step's end is out, its pairing is closed: a row of it that comes later is named by row-seen, after a timed-out hold or an end the turn's completion released", async () => {
    const h = harness()
    await h.ready()
    const named = () => h.events().filter((e) => e.type === 'block-row' || e.type === 'row-seen' || (e.type === 'step' && e.phase === 'end')).map((e) => `${String(e.type)}:${String(e.uuid ?? e.step)}`)
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'late' }])
    await h.fire(STEP_END_WAIT_MS)
    await h.responseRow({ type: 'text', text: 'late' }, { uuid: 'late-row' })
    expect(named()).toEqual(['step:0', 'row-seen:late-row'])
    await h.step({ turnId: 't1', index: 1, model: 'm', messageCount: 3 }, [{ kind: 'text', index: 0, text: 'ended' }])
    await h.complete('t1')
    await h.responseRow({ type: 'text', text: 'ended' }, { uuid: 'after-turn' })
    expect(named()).toEqual(['step:0', 'row-seen:late-row', 'step:1', 'row-seen:after-turn'])
  })

  test('a response row whose block never streamed (a server tool) is noticed by row-seen; a queue record, no row of the conversation, by none', async () => {
    const h = harness()
    await h.ready()
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'a' }], async () => {
      await h.responseRow({ type: 'server_tool_use', id: 'srv_1', name: 'web_search' }, { uuid: 'r-srv' })
      await h.responseRow({ type: 'text', text: 'a' }, { uuid: 'r-a' })
    })
    await h.append('queue', { type: 'user', role: 'user', content: [{ type: 'text', text: 'later' }] }, { uuid: 'q-1' })
    expect(notices(h)).toEqual(['row-seen:r-srv', 'block-row:r-a'])
  })

  test("a hook's success with nothing to say, which the engine raises but never writes to the transcript, is named by none; one with text is", async () => {
    const h = harness()
    await h.ready()
    await h.append('hook-context', { type: 'attachment', name: 'hook_success', role: 'user', content: [] }, { uuid: 'r-empty' })
    await h.append('hook-context', { type: 'attachment', name: 'hook_success', role: 'user', content: [{ type: 'text', text: ' ' }] }, { uuid: 'r-blank' })
    await h.append('hook-context', { type: 'attachment', name: 'hook_success', role: 'user', content: [{ type: 'text', text: 'context' }] }, { uuid: 'r-said' })
    await h.append('hook-context', { type: 'attachment', name: 'hook_permission_decision', role: 'user', content: [] }, { uuid: 'r-mark' })
    expect(notices(h)).toEqual(['row-seen:r-said', 'row-seen:r-mark'])
  })

  test("another plugin's own append (door note), which a hook beneath may refuse, is noticed once it is kept, and never when refused", async () => {
    const h = harness()
    await h.ready()
    let before: string[] = []
    await h.append('note', { type: 'user', role: 'user', content: [{ type: 'text', text: 'n' }] }, {
      uuid: 'r-note',
      next: async (inner) => {
        await h.settle()
        before = notices(h)
        return { message: inner.message, uuid: inner.uuid }
      },
    })
    await h.append('note', { type: 'user', role: 'user', content: [{ type: 'text', text: 'm' }] }, { uuid: 'r-refused', next: async () => ({ deny: 'no' }) })
    expect(before).toEqual([])
    expect(notices(h)).toEqual(['row-seen:r-note'])
  })

  test("the bridge's own steer row, which its hook does not see, is noticed from the append's returned uuid", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'steer', text: 'also print the date' })
    expect(h.ofType('row-seen')).toEqual([expect.objectContaining({ uuid: 'row-1', agentId: null, door: 'note' })])
  })

  test("every resync carries the cut, each loop's last notice (main null when the loop had no rows); a /clear starts it anew", async () => {
    const h = harness()
    await h.ready()
    expect(h.ofType('resync')[0]).toMatchObject({ cut: { main: null } })
    await h.append('prompt', { type: 'user', role: 'user', content: [{ type: 'text', text: 'go' }] }, { uuid: 'r-1' })
    await h.append('attachment', { type: 'attachment', name: 'x', role: 'user', content: [] }, { uuid: 'r-sub', agentId: 'a7' })
    await h.append('tool-result', { type: 'user', role: 'user', content: [{ type: 'tool_result', tool_use_id: 't', content: 'ok' }] }, { uuid: 'r-2' })
    h.children[0]!.write(hello())
    await h.settle()
    expect(h.ofType('resync').at(-1)).toMatchObject({ cut: { main: 'r-2', a7: 'r-sub' } })
    h.setSession('5b000002-0000-4000-8000-00000000005b')
    await h.hook('session.end')(h.engine, { reason: 'clear' }, async () => undefined)
    for (let i = 0; i < 5; i++) {
      await h.fire(100)
    }
    h.children.at(-1)!.write(hello('5b000002-0000-4000-8000-00000000005b', '/tmp/s/bridge/5b000002-0000-4000-8000-00000000005b.sock'))
    await h.settle()
    expect(h.ofType('resync').at(-1)).toMatchObject({ cut: { main: null } })
    expect(Object.keys(h.ofType('resync').at(-1)!.cut as object)).toEqual(['main'])
  })
})

describe("a compaction's rows, which no session.append raises", () => {
  const notices = (h: ReturnType<typeof harness>) =>
    h.events().filter((e) => e.type === 'block-row' || e.type === 'row-seen').map((e) => `${String(e.type)}:${String(e.uuid)}`)
  const prompt = (h: ReturnType<typeof harness>, uuid: string) =>
    h.append('prompt', { type: 'user', role: 'user', content: [{ type: 'text', text: 'go' }] }, { uuid })
  /** A compaction's result as the engine hands it (2.1.301): its summary first, carrying the summary row's uuid as its handle. */
  const result = (summary: string) => ({ messages: [{ role: 'user' as const, text: 'This session is being continued…', toolUses: [], handle: summary }], tokensBefore: 900, tokensAfter: 100 })
  /** The poster's reads of the transcript, each a poll apart. */
  const poll = (h: ReturnType<typeof harness>) => h.fire(ROWS_POLL_MS)

  test("the bridge's compaction: the rows past the cut that no notice named are each named by row-seen (door compaction), in disk order, once its summary row is on disk and a poll later; ahead of its end and of anything later, which waits", async () => {
    const h = harness()
    await h.ready()
    await prompt(h, 'p0')
    h.disk.main = ['p0']
    const r = await h.command({ op: 'compact' })
    h.compactions[0]!.finish(result('sum'))
    await h.settle()
    // The next turn's prompt, named meanwhile: behind the compaction's rows.
    await prompt(h, 'p1')
    expect(h.rowReads[0]).toEqual({ loop: 'main', after: 'p0', socketPath: SOCK })
    expect(notices(h)).toEqual(['row-seen:p0'])
    expect(h.ofType('compact').map((e) => e.phase)).toEqual(['start'])
    h.disk.main = ['p0', 'bound', 'sum']
    await poll(h)
    expect(notices(h)).toEqual(['row-seen:p0'])
    // A poll later the batch is whole; p1, named already, is no compaction row.
    h.disk.main = ['p0', 'bound', 'sum', 'env', 'model', 'p1']
    await poll(h)
    const order = h.events().filter((e) => e.type === 'row-seen' || e.type === 'compact').map((e) => (e.type === 'compact' ? `compact:${String(e.phase)}` : String(e.uuid)))
    expect(order).toEqual(['p0', 'compact:start', 'bound', 'sum', 'env', 'model', 'compact:end', 'p1'])
    expect(h.ofType('row-seen').slice(1, 5)).toEqual(['bound', 'sum', 'env', 'model'].map((uuid) => expect.objectContaining({ uuid, agentId: null, door: 'compaction' })))
    expect(h.ofType('compact').at(-1)).toMatchObject({ phase: 'end', id: r.id, tokensAfter: 100 })
    // The cut is the last notice in the stream's order: p1's.
    h.children[0]!.write(hello())
    await h.settle()
    expect(h.ofType('resync').at(-1)).toMatchObject({ cut: { main: 'p1' } })
  })

  test("with nothing after it, the cut moves to the compaction's last row; a row named again later is not named twice", async () => {
    const h = harness()
    await h.ready()
    await prompt(h, 'p0')
    h.disk.main = ['p0', 'bound', 'sum', 'env']
    await h.command({ op: 'compact' })
    h.compactions[0]!.finish(result('sum'))
    await h.settle()
    await poll(h)
    expect(notices(h)).toEqual(['row-seen:p0', 'row-seen:bound', 'row-seen:sum', 'row-seen:env'])
    h.children[0]!.write(hello())
    await h.settle()
    expect(h.ofType('resync').at(-1)).toMatchObject({ cut: { main: 'env' } })
    // A second compaction reads past the first's last row.
    h.disk.main.push('bound2', 'sum2')
    await h.command({ op: 'compact' })
    h.compactions[1]!.finish(result('sum2'))
    await h.settle()
    await poll(h)
    expect(h.rowReads.at(-1)).toMatchObject({ after: 'env' })
    expect(notices(h).slice(4)).toEqual(['row-seen:bound2', 'row-seen:sum2'])
  })

  test("a compaction this plugin did not start (the person's /compact, through session.compact) is named the same way, a subagent's in its own loop; a precompute, a skipped one, and one whose rows the engine raised (an auto compaction's) read nothing or name nothing more", async () => {
    const h = harness()
    await h.ready()
    await prompt(h, 'p0')
    const compact = (e: Record<string, unknown>, answer: Record<string, unknown>) =>
      h.hook('session.compact', { trigger: e.trigger })(h.engine, { messages: [], ...e }, async () => answer) as Promise<Record<string, unknown>>
    h.disk.main = ['p0', 'bound', 'sum', 'caveat', 'cmd', 'stdout', 'env']
    expect(await compact({ trigger: 'manual' }, result('sum'))).toEqual(result('sum'))
    await h.settle()
    await poll(h)
    expect(notices(h)).toEqual(['row-seen:p0', 'row-seen:bound', 'row-seen:sum', 'row-seen:caveat', 'row-seen:cmd', 'row-seen:stdout', 'row-seen:env'])
    const reads = h.rowReads.length
    await compact({ trigger: 'precompute' }, result('pre'))
    await compact({ trigger: 'manual' }, { skip: 'a hook said no' })
    await h.settle()
    await poll(h)
    expect(h.rowReads.length).toBe(reads)
    // An auto compaction: the engine raises its rows, each named by its append.
    await compact({ trigger: 'auto' }, result('sum3'))
    await h.append('compaction', { type: 'system', name: 'compact_boundary', content: [] }, { uuid: 'bound3' })
    await h.append('compaction', { type: 'user', role: 'user', content: [{ type: 'text', text: 'summary' }] }, { uuid: 'sum3' })
    h.disk.main.push('bound3', 'sum3')
    await poll(h)
    await poll(h)
    expect(notices(h).slice(7)).toEqual(['row-seen:bound3', 'row-seen:sum3'])
    expect(h.ofType('row-seen').slice(7).map((e) => e.door)).toEqual(['compaction', 'compaction'])
    // A subagent's loop: its own cut, its own transcript, its id.
    await h.append('attachment', { type: 'attachment', name: 'x', role: 'user', content: [] }, { uuid: 's0', agentId: 'a7' })
    h.disk.a7 = ['s0', 's-bound', 's-sum']
    await compact({ trigger: 'auto', agentId: 'a7' }, result('s-sum'))
    await h.settle()
    await poll(h)
    expect(h.rowReads.at(-1)).toMatchObject({ loop: 'a7', after: 's0' })
    expect(h.ofType('row-seen').slice(-2)).toEqual(['s-bound', 's-sum'].map((uuid) => expect.objectContaining({ uuid, agentId: 'a7', door: 'compaction' })))
  })

  test("another mod's compaction (the compact tool's) is named ahead of the resume prompt the mod submits after it", async () => {
    const h = harness()
    await h.ready()
    await prompt(h, 'p0')
    h.disk.main = ['p0']
    compacted(null, result('sum').messages)
    await prompt(h, 'resume')
    h.disk.main = ['p0', 'bound', 'sum', 'env', 'resume']
    await poll(h)
    await poll(h)
    expect(notices(h)).toEqual(['row-seen:p0', 'row-seen:bound', 'row-seen:sum', 'row-seen:env', 'row-seen:resume'])
  })

  test('rows not on disk within ROWS_POLLS reads are left unnamed, and what the hold kept goes out; with no cut yet nothing is held', async () => {
    const h = harness()
    await h.start()
    // Before the first hello, the main loop of a reloaded session has no cut: nothing to read past.
    compacted(null, result('early').messages)
    h.children[0]!.write(hello())
    await h.settle()
    await prompt(h, 'p0')
    // A result whose summary has no handle (a hook answered with messages of its own): nothing says when its rows are in.
    const built = [{ role: 'user' as const, text: 'a summary of its own', toolUses: [] }]
    compacted(null, built)
    await h.settle()
    expect(h.rowReads.length).toBe(0)
    h.disk.main = ['p0']
    compacted(null, result('sum').messages)
    await prompt(h, 'p1')
    for (let i = 0; i < ROWS_POLLS; i++) {
      await poll(h)
    }
    expect(h.rowReads.length).toBe(ROWS_POLLS)
    expect(notices(h)).toEqual(['row-seen:p0', 'row-seen:p1'])
  })

  test("a hello during the hold: the new child's resync comes first, then the compaction's rows while the cut is still where they begin; a later notice that moved the cut drops them (the resync's cut covers them)", async () => {
    const h = harness()
    await h.ready()
    await prompt(h, 'p0')
    h.disk.main = ['p0']
    compacted(null, result('sum').messages)
    await h.settle()
    h.children[0]!.write(hello())
    await h.settle()
    h.disk.main = ['p0', 'bound', 'sum']
    await poll(h)
    await poll(h)
    const tail = h.events().slice(-4).map((e) => `${e.type}${e.uuid === undefined ? '' : `:${String(e.uuid)}`}`)
    expect(tail).toEqual(['session', 'resync', 'row-seen:bound', 'row-seen:sum'])
    // Again, with a later row named before the hello: its cut covers the compaction's rows.
    h.disk.main.push('bound2', 'sum2', 'p2')
    compacted(null, result('sum2').messages)
    await prompt(h, 'p2')
    h.children[0]!.write(hello())
    await h.settle()
    await poll(h)
    await poll(h)
    expect(h.ofType('resync').at(-1)).toMatchObject({ cut: { main: 'p2' } })
    expect(notices(h).slice(-1)).toEqual(['row-seen:sum'])
    expect(h.events().at(-1)).toMatchObject({ type: 'resync' })
  })

  test('with the poster behind, two compactions and a response row between them all on disk before the first hold runs: each hold names only the rows before the first a notice queued behind it names', async () => {
    const h = harness({ hold: true })
    await h.ready()
    // The hello's post is held: everything after it queues.
    await prompt(h, 'p0')
    compacted(null, result('s1').messages)
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'Hi' }], async () => {
      await h.responseRow({ type: 'text', text: 'Hi' }, { uuid: 'r' })
    })
    compacted(null, result('s2').messages)
    h.disk.main = ['p0', 'b1', 's1', 'r', 'b2', 's2']
    for (let i = 0; i < 10; i++) {
      h.posts.forEach((p) => p.release())
      await poll(h)
    }
    expect(notices(h)).toEqual(['row-seen:p0', 'row-seen:b1', 'row-seen:s1', 'block-row:r', 'row-seen:b2', 'row-seen:s2'])
    h.children[0]!.write(hello())
    await h.settle()
    expect(h.ofType('resync').at(-1)).toMatchObject({ cut: { main: 's2' } })
  })

  test("a row named before the hold stays named whatever traffic comes before or after it (another loop's, or the loop's own queued behind the hold): the compaction's rows are named once, and no row twice", async () => {
    const h = harness()
    await h.ready()
    await prompt(h, 'p0')
    // Named before the hold, though the engine wrote it past the cut (its write order).
    await prompt(h, 'a')
    // A subagent's notices, more than any bound keeps, before the hold.
    for (let i = 0; i < 1_001; i++) {
      await h.append('attachment', { type: 'attachment', name: 'x', role: 'user', content: [] }, { uuid: `s${i}`, agentId: 'a7' })
    }
    await prompt(h, 'z')
    h.disk.main = ['p0', 'z', 'a', 'bound', 'sum', 'm0', 'm1']
    compacted(null, result('sum').messages)
    // The loop's own notices queued behind the hold, more than its bound keeps; the first two are on disk.
    const later = Array.from({ length: 202 }, (_, i) => `m${i}`)
    for (const uuid of later) {
      await prompt(h, uuid)
    }
    await poll(h)
    await poll(h)
    const main = h.ofType('row-seen').filter((e) => e.agentId === null).map((e) => String(e.uuid))
    expect(main).toEqual(['p0', 'a', 'z', 'bound', 'sum', ...later])
    expect(h.ofType('row-seen').filter((e) => e.door === 'compaction').map((e) => e.uuid)).toEqual(['bound', 'sum'])
  })

  test("two compactions with nothing of their loop named between them share an anchor: the second reads past the first's rows, and the cut moves to its own last row", async () => {
    const h = harness()
    await h.ready()
    await prompt(h, 'p0')
    h.disk.main = ['p0']
    compacted(null, result('s1').messages)
    compacted(null, result('s2').messages)
    h.disk.main.push('b1', 's1')
    await poll(h)
    await poll(h)
    expect(notices(h)).toEqual(['row-seen:p0', 'row-seen:b1', 'row-seen:s1'])
    h.disk.main.push('b2', 's2')
    await poll(h)
    await poll(h)
    expect(notices(h)).toEqual(['row-seen:p0', 'row-seen:b1', 'row-seen:s1', 'row-seen:b2', 'row-seen:s2'])
    h.children[0]!.write(hello())
    await h.settle()
    expect(h.ofType('resync').at(-1)).toMatchObject({ cut: { main: 's2' } })
    expect(h.rowReads.at(-1)).toMatchObject({ after: 's1' })
  })

  test("two holds at a subagent's cut with a notice of it queued behind them: the rows the first names count as named for the second, though the cut is that notice's and the subagent stopped in between", async () => {
    const h = harness({ hold: true })
    await h.ready()
    const attachment = (uuid: string) => h.append('attachment', { type: 'attachment', name: 'x', role: 'user', content: [] }, { uuid, agentId: 'a7' })
    await attachment('q0')
    compacted('a7', result('s1').messages)
    compacted('a7', result('s2').messages)
    await attachment('r')
    h.disk.a7 = ['q0', 'b1', 's1', 'b2', 's2', 'r']
    // The hello's post, then q0's; the first hold runs, and the post of what it named is held.
    h.posts[0]!.release()
    await h.settle()
    h.posts[1]!.release()
    await poll(h)
    await poll(h)
    expect(h.posts).toHaveLength(3)
    await h.hook('classic.SubagentStop', { hook_event_name: 'SubagentStop' })(h.engine, { hook_event_name: 'SubagentStop', agent_id: 'a7', agent_type: 'Explore' }, async () => ({}))
    for (let i = 0; i < 6; i++) {
      h.posts.forEach((p) => p.release())
      await poll(h)
    }
    expect(notices(h)).toEqual(['row-seen:q0', 'row-seen:b1', 'row-seen:s1', 'row-seen:b2', 'row-seen:s2', 'row-seen:r'])
  })
})

describe('the seed: each loop cut at load', () => {
  /** A module loaded into a session that already had its conversation (a reload, a resume). */
  const RELOADED = { messages: [{ role: 'user', text: 'earlier' }] }
  const notices = (h: ReturnType<typeof harness>) =>
    h.events().filter((e) => e.type === 'block-row' || e.type === 'row-seen').map((e) => `${String(e.type)}:${String(e.uuid)}`)
  const streamed = (h: ReturnType<typeof harness>, turnId: string) => h.events().filter((e) => (e.type === 'chunk' || e.type === 'step') && e.turnId === turnId)
  /** A model request whose chunks come as the test releases them, with its hook's iteration running meanwhile. */
  const openStep = (h: ReturnType<typeof harness>, e: Record<string, unknown>) => {
    const queued: Record<string, unknown>[] = []
    let wake: (() => void) | undefined
    let isDone = false
    const result = { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: 'end_turn', usage: null }
    const next = () => {
      const g = (async function* () {
        for (;;) {
          const c = queued.shift()
          if (c !== undefined) {
            yield c
            continue
          }
          if (isDone) {
            return result
          }
          await new Promise<void>((resolve) => (wake = resolve))
        }
      })() as AsyncGenerator<Record<string, unknown>, unknown> & { result: Promise<unknown> }
      g.result = Promise.resolve(result)
      return g
    }
    const gen = h.hook('turn.step', e)(h.engine, e, next) as AsyncGenerator<Record<string, unknown>, unknown>
    const drained = (async () => {
      for (;;) {
        if ((await gen.next()).done) {
          return
        }
      }
    })()
    return {
      chunk: async (c: Record<string, unknown>) => {
        queued.push(c)
        wake?.()
        await h.settle()
      },
      end: async () => {
        isDone = true
        wake?.()
        await drained
        await h.settle()
      },
    }
  }

  test("the first hello's seed is each loop's cut: the last row each loop had when the child read the transcripts", async () => {
    const h = harness(RELOADED)
    await h.start()
    h.children[0]!.write(hello(SID, SOCK, undefined, NONCE, { main: 'm-9', a7: 's-3' }))
    await h.settle()
    expect(h.ofType('resync')[0]).toMatchObject({ cut: { main: 'm-9', a7: 's-3' } })
  })

  test("a loop noticed before the hello keeps its notice (its rows past the seed are each noticed in turn); a later child's hello seeds nothing", async () => {
    const h = harness(RELOADED)
    await h.start()
    await h.append('prompt', { type: 'user', role: 'user', content: [{ type: 'text', text: 'go' }] }, { uuid: 'm-10' })
    h.children[0]!.write(hello(SID, SOCK, undefined, NONCE, { main: 'm-9', a7: 's-3' }))
    await h.settle()
    expect(h.ofType('resync')[0]).toMatchObject({ cut: { main: 'm-10', a7: 's-3' } })
    h.children[0]!.end()
    await h.settle()
    h.timers.find((t) => t.kind === 'after')!.fn()
    await h.settle()
    h.children[1]!.write(hello(SID, SOCK, undefined, 'n1', { main: 'm-77', a8: 's-1' }))
    await h.settle()
    expect(h.ofType('resync').at(-1)!.cut).toEqual({ main: 'm-10', a7: 's-3' })
  })

  test('the race: a message that began before the seed, its row flushed before the read, never streams; its rows are named by row-seen', async () => {
    const h = harness(RELOADED)
    await h.start()
    await h.turn('t1')
    const m = openStep(h, { turnId: 't1', index: 0, model: 'm', messageCount: 1 })
    await m.chunk({ kind: 'text', index: 0, text: 'Hi' })
    await h.append('response', { type: 'assistant', role: 'assistant', content: [{ type: 'text', text: 'Hi' }] }, { uuid: 'r-hi', origin: { kind: 'model', model: 'm' } })
    // The child read the transcript after that row was flushed: it is the seed.
    h.children[0]!.write(hello(SID, SOCK, undefined, NONCE, { main: 'r-hi' }))
    await h.settle()
    await m.chunk({ kind: 'tool', index: 1, id: 'toolu_1', name: 'Bash' })
    await h.append('response', { type: 'assistant', role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_1', name: 'Bash', input: {} }] }, { uuid: 'r-tool', origin: { kind: 'model', model: 'm' } })
    await m.end()
    const resync = h.ofType('resync')[0]!
    expect(resync).toMatchObject({ streaming: [], cut: { main: 'r-hi' } })
    expect(streamed(h, 't1')).toEqual([])
    // r-hi's notice came before the hello: the resync's cut accounts for it.
    expect(notices(h)).toEqual(['row-seen:r-tool'])
  })

  test('the inverse: a message beginning while the read is in flight, its rows all written after it, is excluded too', async () => {
    const h = harness(RELOADED)
    await h.start()
    await h.turn('t1')
    const m = openStep(h, { turnId: 't1', index: 0, model: 'm', messageCount: 1 })
    h.children[0]!.write(hello(SID, SOCK, undefined, NONCE, { main: 'r-0' }))
    await h.settle()
    await m.chunk({ kind: 'text', index: 0, text: 'late' })
    await h.append('response', { type: 'assistant', role: 'assistant', content: [{ type: 'text', text: 'late' }] }, { uuid: 'r-late', origin: { kind: 'model', model: 'm' } })
    await m.end()
    expect(h.ofType('resync')[0]).toMatchObject({ streaming: [], cut: { main: 'r-0' } })
    expect(streamed(h, 't1')).toEqual([])
    expect(notices(h)).toEqual(['row-seen:r-late'])
    // The next request, begun after the seed, streams and pairs its rows.
    const { yielded } = await h.step({ turnId: 't1', index: 1, model: 'm', messageCount: 3 }, [{ kind: 'text', index: 0, text: 'on' }], async () => {
      await h.responseRow({ type: 'text', text: 'on' }, { uuid: 'r-on' })
    })
    expect(yielded.length).toBe(1)
    expect(streamed(h, 't1').map((e) => e.type)).toEqual(['step', 'chunk', 'step'])
    expect(notices(h)).toEqual(['row-seen:r-late', 'block-row:r-on'])
  })

  test('a session the module started with (no message at load): its first request, begun before the hello, still streams; no seed is taken for it', async () => {
    const h = harness()
    await h.start()
    await h.turn('t1')
    const m = openStep(h, { turnId: 't1', index: 0, model: 'm', messageCount: 1 })
    await m.chunk({ kind: 'text', index: 0, text: 'READY' })
    h.children[0]!.write(hello(SID, SOCK, undefined, NONCE, { main: 'r-prompt' }))
    await h.settle()
    const resync = h.ofType('resync')[0]!
    expect(resync.cut).toEqual({ main: null })
    expect(resync.streaming).toEqual([expect.objectContaining({ turnId: 't1', blocks: [expect.objectContaining({ text: 'READY' })] })])
    await m.chunk({ kind: 'text', index: 0, text: '!' })
    await h.responseRow({ type: 'text', text: 'READY!' }, { uuid: 'r-ready' })
    await m.end()
    expect(h.ofType('chunk').map((e) => (e.chunk as { text: string }).text)).toEqual(['!'])
    expect(notices(h)).toEqual(['block-row:r-ready'])
  })

  test('a subagent the module saw spawned streams before the hello and takes no seed; one running at load is seeded and held back', async () => {
    const h = harness(RELOADED)
    await h.start()
    const spawn = { tool_use_id: 'tu', subagentType: 'general-purpose', description: 'd', background: true }
    await h.hook('agent.spawn', spawn)(h.engine, spawn, async () => ({ model: 'm', agentId: 'a-new' }))
    const fresh = openStep(h, { turnId: 'ts', index: 0, model: 'm', messageCount: 1, agentId: 'a-new' })
    const old = openStep(h, { turnId: 'to', index: 0, model: 'm', messageCount: 1, agentId: 'a-old' })
    await fresh.chunk({ kind: 'text', index: 0, text: 'new' })
    await old.chunk({ kind: 'text', index: 0, text: 'old' })
    h.children[0]!.write(hello(SID, SOCK, undefined, NONCE, { main: 'm-1', 'a-new': 's-new', 'a-old': 's-old' }))
    await h.settle()
    const resync = h.ofType('resync')[0]!
    expect(resync.cut).toEqual({ main: 'm-1', 'a-old': 's-old' })
    expect((resync.streaming as { agentId: string }[]).map((m) => m.agentId)).toEqual(['a-new'])
    await fresh.end()
    await old.end()
  })
})
