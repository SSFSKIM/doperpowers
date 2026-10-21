import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import { ASK_TOOL, ASYNC_RESULT, PLUGIN, deliveryText, registerAsk, resetAsk } from '../../hooks/mods/ask'
import {
  AGENTS_REFRESH_MS,
  BACKGROUND_WINDOW_MS,
  BLOCK_TAIL,
  HEARTBEAT_MS,
  INTERRUPT_HOLD_MS,
  OFF_LINE,
  ON_LINE,
  RECORD_WAIT_MS,
  ROWS_POLLS,
  ROWS_POLL_MS,
  RESYNC_INPUT_CAP,
  RESYNC_MAX,
  STEER_LINE,
  STEP_END_WAIT_MS,
  TRANSCRIPT_RETRY_MS,
  TEXT_CAP,
  compacted,
  onAskNote,
  registerBridge,
  resetBridge,
  splitLines,
  stopNote,
  wakeText,
} from '../../hooks/mods/bridge'

tier('user')

const SID = '5b000001-0000-4000-8000-00000000005b'
const SOCK = `/tmp/s/bridge/${SID}.sock`
const NONCE = 'n0'
const hello = (session = SID, socket = SOCK, kept?: Record<string, unknown>, nonce = NONCE, seed?: Record<string, string>) =>
  `${JSON.stringify({ op: 'hello', session, pid: 7, socket, protocol: 1, nonce, ...(kept !== undefined && { kept }), ...(seed !== undefined && { seed }) })}\n`
const line = (obj: Record<string, unknown>) => `${JSON.stringify(obj)}\n`
/** A steer's row and a delivered message's, as a wake counts them. */
const NOTE = {}
const MESSAGE = (frame?: string) => ({ isDelivery: true, ...(frame !== undefined && { frame }) })
/**
 * A `next` as the engine hands it to a hook, once it settled: `next.trace`
 * lists the links beneath, one per plugin's module, nearest first, and the
 * engine's own entry last, unless a link answered the call itself (`short`);
 * `next.origin` names the plugin that raised the dispatch, the engine when
 * none did. A `next` that names its origin already keeps it.
 */
const beneath = <T extends object>(next: T, plugins: readonly string[], options: { short?: boolean; origin?: string } = {}) => {
  const links = [...plugins, ...(options.short === true ? [] : ['engine'])]
  const trace = links.map((plugin, i) => ({ index: i + 1, plugin, tier: plugin === 'engine' ? 'core' : 'user', event: 'tool.call', outcome: 'returned', ms: 0, received: {}, returned: undefined }))
  const origin = options.origin === undefined ? { plugin: 'engine', tier: 'core' } : { plugin: options.origin, tier: 'user' }
  return Object.assign(next, { trace }, 'origin' in next && options.origin === undefined ? {} : { origin })
}
/** devcloud's marker as its loaded module answers it (at version 0), and as an older devcloud stored it (version 1), which outlives its module. */
/** The longest body `$.http.fetch` sends, in characters. */
const ENGINE_BODY_MAX = 4_194_304
const LIVE_MARKER = { value: { owner: 'devcloud', version: 1 }, version: 0 }
const STORED_MARKER = { value: { owner: 'devcloud', version: 1 }, version: 1 }

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
    // A child the stream's `return()` stopped has no exit to report: the
    // engine (2.1.304) settles the result with nothing then.
    get result() {
      return Promise.resolve(killed ? undefined : { code: 0, signal: null })
    },
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
    /** TaskStop never answers. */
    taskStopHangs?: boolean
    denyAppend?: string
    /** `$.turn.abort` rejects, as it does when the turn is no longer running. */
    abortFails?: boolean
    /** What `$.session.messages()` answers at load: none, a session the module starts with; some, a reload or a resume. */
    messages?: unknown[]
    /** What `$.agent.list()` answers at load (setAgents changes it later). */
    agents?: Record<string, unknown>[]
    /** `$.prompt.submit` resolves dropped, with this reason. */
    submitDrops?: string
    /** `$.prompt.submit` waits until the test settles it (`submits`), as a prompt taken does until its turn starts. */
    holdSubmit?: boolean
    /**
     * No row of the session has been kept when it starts, so the bridge has no
     * verdict on its place. Otherwise `start` lands one, as a placed session's
     * first row does.
     */
    verdictPending?: boolean
    /** What devcloud's marker reads as (`$.state.get`): by default nothing, at version 0, as with devcloud not loaded. */
    marker?: { value: unknown; version: number }
    /** The user settings enable `cua@cua`. */
    cua?: boolean
    /** `$.state.get` rejects. */
    stateFails?: boolean
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
    /** The body's length in characters. */
    size: number
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
  const toasts: string[] = []
  /** What the bridge read to learn which secrets guard is loaded: devcloud's marker, the user settings. */
  const guardReads: { op: string; args: unknown }[] = []
  let marker = options.marker ?? { value: undefined, version: 0 }
  let isCuaEnabled = options.cua === true
  /** While held (`holdGuardReads`), `$.state.get` waits. */
  let readGate: Promise<void> = Promise.resolve()
  /** What the control ops asked of the engine, in order. */
  const calls: { op: string; args: unknown }[] = []
  const compactions: { args: unknown; finish: (outcome: Record<string, unknown>) => void; fail: (error: Error) => void }[] = []
  /** Appends held by `holdAppend`, each released by the test. */
  const appends: (() => void)[] = []
  /** Submits held by `holdSubmit`, each settled by the test with what `$.prompt.submit` resolves to. */
  const submits: ((entered: Record<string, unknown>) => void)[] = []
  /** The rows the mod's appends put in the main conversation, in order; and what each model request carried of them. */
  const conversation: { type: string; content: { type: string; text: string }[] }[] = []
  const requests: (typeof conversation)[] = []
  /** The turns `$.turn.abort` cancelled. */
  const aborted = new Set<string>()
  /** The calls `called` keeps running, each ended by the test or by an abort. */
  const running: ((result: Record<string, unknown>) => void)[] = []
  /** Files `$.fs.read` reads (the session's transcripts). */
  const files: Record<string, string> = {}
  /** Each loop's rows on disk, as the child's GET /rows reads them; and the reads made. */
  const disk: Record<string, string[]> = {}
  const rowReads: { loop: string | null; after: string | null; socketPath?: string }[] = []
  let session = SID
  /** What `$.session.messages({ as: "api" })` answers when a test set it; and how many times it was read. */
  let apiConversation: unknown[] | undefined
  let apiReads = 0
  /** While held (`holdApiReads`), `$.session.messages({ as: "api" })` waits. */
  let apiGate: Promise<void> = Promise.resolve()
  let listedAgents = options.agents ?? []
  /** How many times the mod read `$.agent.list()`. */
  let agentLists = 0
  const $ = {
    plugin: { name: PLUGIN, root: '/plug' },
    env: { get: async (name: string) => options.env?.[name] },
    session: {
      id: async () => session,
      model: async () => 'claude-haiku',
      version: async () => ({ version: '2.1.300' }),
      // As the requests read it (`as: "api"`): the mod's appended rows, unless a test rewound it.
      messages: async (args?: { as?: string }) => {
        if (args?.as !== 'api') {
          return options.messages ?? []
        }
        apiReads++
        await apiGate
        return apiConversation ?? conversation.map((m) => ({ role: 'user', content: m.content }))
      },
      usage: async () => ({ startedAt: 0, context: { tokens: 5000, window: 200000, percent: 2 }, rateLimits: [] }),
      append: (args: unknown) => {
        calls.push({ op: 'append', args })
        const denied = options.denyAppend !== undefined && JSON.stringify(args).includes(options.denyAppend)
        const stored = denied ? { deny: 'refused by a hook' } : { uuid: `row-${calls.length}`, message: {} }
        const keep = () => {
          if (!denied) {
            conversation.push((args as { message: (typeof conversation)[number] }).message)
          }
          return stored
        }
        if (!options.holdAppend) {
          return Promise.resolve(keep())
        }
        return new Promise((resolve) => appends.push(() => resolve(keep())))
      },
      compact: (args: unknown) => {
        calls.push({ op: 'compact', args })
        return new Promise((resolve, reject) => compactions.push({ args, finish: resolve, fail: reject }))
      },
    },
    turn: {
      abort: async (args: { turnId: string }) => {
        calls.push({ op: 'abort', args })
        if (options.abortFails) {
          throw new Error('$.turn.abort: no turn is running')
        }
        // As the engine: a turn already cancelled is refused.
        if (aborted.has(args.turnId)) {
          throw new Error(`$.turn.abort: ${args.turnId} is already ending`)
        }
        aborted.add(args.turnId)
        // As the engine's abort ends the turn's running calls.
        for (const end of running.splice(0)) {
          end({ text: 'Interrupted by user', isError: true })
        }
      },
    },
    tool: {
      call: async (args: Record<string, unknown>) => {
        calls.push({ op: 'tool', args })
        if (options.taskStopHangs) {
          return new Promise(() => undefined)
        }
        if (options.taskStopFails?.includes(String(args.task_id))) {
          return { text: `No task found with ID: ${String(args.task_id)}`, isError: true }
        }
        return { text: `Successfully stopped task: ${String(args.task_id)}` }
      },
    },
    prompt: {
      submit: async (args: unknown) => {
        calls.push({ op: 'submit', args })
        if (options.holdSubmit) {
          return new Promise((resolve) => submits.push(resolve))
        }
        return options.submitDrops !== undefined ? { drop: options.submitDrops } : { text: String((args as { text?: unknown }).text) }
      },
    },
    agent: {
      list: async () => {
        agentLists++
        return listedAgents.map((a) => ({ ...a }))
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
          const body = init.body ?? '[]'
          posts.push({ url, socketPath: init.socketPath, nonce: init.headers?.['x-bridge-nonce'], events: JSON.parse(body), size: body.length, release, fail, refuse })
          // As the engine (2.1.300): a body past its limit is refused before it is sent.
          if (body.length > ENGINE_BODY_MAX) {
            reject(new Error(`the request body is ${body.length} characters, over ${ENGINE_BODY_MAX}`))
            return
          }
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
    ui: { log: (text: string) => logs.push(text), toast: (text: string) => toasts.push(text), notify: async () => ({ isSent: true, channel: 'terminal_bell' }) },
    state: {
      get: async (ref: { plugin: string; key: string }) => {
        guardReads.push({ op: 'state.get', args: ref })
        await readGate
        if (options.stateFails) {
          throw new Error('$.state.get: the host did not answer')
        }
        return ref.plugin === 'devcloud' && ref.key === 'secrets-guard' ? marker : { value: undefined, version: 0 }
      },
    },
    settings: {
      read: async (args?: { source?: string }) => {
        guardReads.push({ op: 'settings.read', args })
        return args?.source === 'user' && isCuaEnabled ? { enabledPlugins: { 'cua@cua': true } } : {}
      },
    },
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
    const handler = found[0]!.handler
    if (event !== 'tool.call' && event !== 'session.append') {
      return handler
    }
    // The engine's `next` always carries what settled beneath it: a test's
    // own names no plugin's link, only the engine's.
    return (engine: unknown, input: unknown, next: unknown) => handler(engine, input, typeof next === 'function' && !('trace' in next) ? beneath(next, []) : next)
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
    if (!options.verdictPending) {
      // The session's first row, kept beneath both guards, lands the bridge's
      // verdict on its place. Refused here, so it posts no notice and each
      // test's posts start where they did.
      const firstRow = { door: 'prompt', message: { type: 'user', content: [] }, uuid: 'first-row', origin: { kind: 'composer' } }
      await hook('session.append', { door: 'prompt' })(engine, firstRow, beneath(async () => ({ deny: 'the harness' }), ['devcloud', 'cua'], { short: true }))
    }
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
      // The request is made now, with the conversation as it stands.
      requests.push([...conversation])
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
  /**
   * A call as the model made it, through the bridge's tool.call hook, put to
   * the dialog by the engine's check beneath it, which holds `checked` (the
   * call's own input unless a hook beneath rewrote it). It runs on, as a call
   * does while its dialog is up, until `end` or an abort.
   */
  const called = async (toolUseId: string, tool: string, input: Record<string, unknown>, agentId?: string, checked: unknown = input) => {
    let end: (result: Record<string, unknown>) => void = () => undefined
    const ran = hook('tool.call', { tool })(engine, { tool, tool_use_id: toolUseId, ...input, ...(agentId !== undefined && { agentId }) }, async () => {
      await check(toolUseId, tool, checked, agentId)
      return new Promise((resolve) => running.push((end = resolve)))
    }) as Promise<Record<string, unknown>>
    await settle()
    return {
      ran,
      end: (result: Record<string, unknown> = { text: 'done' }) => {
        end(result)
        return ran
      },
    }
  }
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
    called,
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
    submits,
    conversation,
    requests,
    command,
    turn,
    complete,
    posts,
    timers,
    logs,
    toasts,
    guardReads,
    setMarker: (read: { value: unknown; version: number }) => (marker = read),
    setCua: (isEnabled: boolean) => (isCuaEnabled = isEnabled),
    /** Holds the guard reads until the returned function is called. */
    holdGuardReads: () => {
      let release: () => void = () => undefined
      readGate = new Promise((resolve) => (release = resolve))
      return release
    },
    settle,
    events,
    ofType,
    start,
    ready,
    step,
    setSession: (id: string) => (session = id),
    setAgents: (agents: Record<string, unknown>[]) => (listedAgents = agents),
    setApiConversation: (messages: unknown[] | undefined) => (apiConversation = messages),
    /** Holds the next reads of the conversation as the requests read it until the returned function is called. */
    holdApiReads: () => {
      let release: () => void = () => undefined
      apiGate = new Promise((resolve) => (release = resolve))
      return release
    },
    apiReads: () => apiReads,
    agentLists: () => agentLists,
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

  test('a child that ends is followed by a new one at once, then later each time it ends at once', async () => {
    const h = harness()
    await h.start()
    h.children[0]!.end()
    await h.settle()
    const respawns = () => h.timers.filter((t) => t.kind === 'after')
    expect(respawns().map((t) => t.ms)).toEqual([0])
    respawns()[0]!.fn()
    await h.settle()
    expect(h.children.length).toBe(2)
    expect(h.children[1]!.argv).toEqual(h.children[0]!.argv)
    // One extra immediate try is all a child that dies at once costs; then a second, doubling.
    for (const i of [1, 2]) {
      h.children[i]!.end()
      await h.settle()
      respawns().at(-1)!.fn()
      await h.settle()
    }
    expect(respawns().map((t) => t.ms)).toEqual([0, 1000, 2000])
    expect(h.children.length).toBe(4)
  })

  test('a child that ends after a stable run is followed by a new one at once, whatever the ones before it cost', async () => {
    const h = harness()
    await h.start()
    const respawns = () => h.timers.filter((t) => t.kind === 'after')
    for (const _ of [0, 1, 2]) {
      h.children.at(-1)!.end()
      await h.settle()
      respawns().at(-1)!.fn()
      await h.settle()
    }
    expect(respawns().map((t) => t.ms)).toEqual([0, 1000, 2000])
    // This one runs 30 s (STABLE_MS, by the engine's clock) before it ends.
    h.advance(30_000)
    h.children.at(-1)!.end()
    await h.settle()
    expect(respawns().map((t) => t.ms)).toEqual([0, 1000, 2000, 0])
  })

  test("a post in flight when its child dies fails without holding up the successor: the successor's session start and resync go at once", async () => {
    const h = harness({ hold: true })
    const releaseAll = async () => {
      for (let i = 0; i < h.posts.length; i++) {
        h.posts[i]!.release()
        await h.settle()
      }
    }
    await h.ready()
    await releaseAll()
    await h.turn('t1')
    await h.settle()
    const inFlight = h.posts.at(-1)!
    const timers = h.timers.length
    h.children[0]!.end()
    await h.settle()
    h.timers[timers]!.fn()
    await h.settle()
    h.children[1]!.write(hello(SID, SOCK, undefined, 'n1'))
    await h.settle()
    inFlight.fail()
    await h.settle()
    expect(h.timers.filter((t) => t.kind === 'after' && t.ms === 500).length).toBe(0)
    const start = h.posts.at(-1)!
    expect([start.nonce, start.events.map((e) => e.type)]).toEqual(['n1', ['session']])
    start.release()
    await h.settle()
    expect(h.posts.at(-1)!.events.map((e) => e.type)).toEqual(['resync'])
  })

  test("a retry's wait set for a child that then died does not hold up its successor, nor does its end clear the successor's own", async () => {
    const h = harness({ hold: true })
    const releaseAll = async () => {
      for (let i = 0; i < h.posts.length; i++) {
        h.posts[i]!.release()
        await h.settle()
      }
    }
    await h.ready()
    await releaseAll()
    await h.turn('t1')
    await h.settle()
    // The post fails while its child still stands: the retry waits RETRY_MS.
    h.posts.at(-1)!.fail()
    await h.settle()
    const obsolete = h.timers.filter((t) => t.kind === 'after' && t.ms === 500)
    expect(obsolete.length).toBe(1)
    const timers = h.timers.length
    h.children[0]!.end()
    await h.settle()
    h.timers[timers]!.fn()
    await h.settle()
    h.children[1]!.write(hello(SID, SOCK, undefined, 'n1'))
    await h.settle()
    const start = h.posts.at(-1)!
    expect([start.nonce, start.events.map((e) => e.type)]).toEqual(['n1', ['session']])
    // The successor's own post fails: its wait stands through the obsolete one's end.
    start.fail()
    await h.settle()
    const posted = h.posts.length
    obsolete[0]!.fn()
    await h.settle()
    expect(h.posts.length).toBe(posted)
    h.timers.filter((t) => t.kind === 'after' && t.ms === 500).at(-1)!.fn()
    await h.settle()
    expect(h.posts.length).toBe(posted + 1)
    expect(h.posts.at(-1)!.events.map((e) => e.type)).toEqual(['gap'])
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
    // The stopped child is not respawned, and is said to be stopped, not to have failed.
    expect(h.timers.filter((t) => t.kind === 'after').length).toBe(0)
    expect(h.logs).toContain('bridge: the child was stopped')
    expect(h.logs.filter((l) => l.startsWith('bridge: the child failed'))).toEqual([])
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
    expect(h.posts.slice(before).map((p) => p.nonce)).toEqual(['n1', 'n1'])
    // The session's start, then the resync in a post of its own.
    expect(h.posts.slice(before).map((p) => p.events.map((e) => e.type))).toEqual([['session'], ['resync']])
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
    expect(h.posts[1]!.events.map((e) => e.type)).toEqual(['session'])
    h.posts[1]!.release()
    await h.settle()
    expect(h.posts.length).toBe(3)
    expect(h.posts[2]!.nonce).toBe('n1')
    expect(h.posts[2]!.events.map((e) => e.type)).toEqual(['resync'])
  })

  test("the first post lost (session start and all): the recovery's resync carries the session's start info, which the child takes", async () => {
    const h = harness({ failAt: [0] })
    await h.ready()
    expect(h.posts[0]!.events.map((e) => e.type)).toEqual(['session'])
    await h.fire(500)
    expect(h.posts.slice(1).map((p) => p.events.map((e) => e.type))).toEqual([['gap'], ['resync']])
    expect(h.posts[2]!.events[0]).toMatchObject({ sessionInfo: { session: SID, cwd: '/w', surface: 'terminal', isInteractive: true, model: 'claude-haiku', version: '2.1.300' } })
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
    // The resync goes alone, and what came meanwhile after it.
    expect(h.posts.length).toBe(2)
    expect(h.posts[1]!.events.map((e) => e.type)).toEqual(['resync'])
    h.posts[1]!.release()
    await h.settle()
    expect(h.posts.length).toBe(3)
    expect(h.posts[2]!.events.map((e) => e.turnId)).toEqual(['t1', 't2'])
  })

  test('a post lost mid-message: the next opens with the gap and a resync whose text covers its upTo', async () => {
    const h = harness({ hold: true })
    await h.start()
    h.children[0]!.write(hello())
    await h.settle()
    // The session's start, then its resync.
    h.posts[0]!.release()
    await h.settle()
    h.posts[1]!.release()
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
    await gen.next() // step start posted (2); A queued
    await h.settle()
    h.posts[2]!.release()
    await h.settle()
    expect(h.posts[3]!.events).toMatchObject([{ type: 'chunk', ...tag, chunkIndex: 0 }])
    await gen.next() // B queued behind the post of A
    await h.settle()
    h.posts[3]!.fail() // A and B never reach the child
    await h.settle()
    expect(h.posts.length).toBe(4) // the next post waits
    h.timers.filter((t) => t.kind === 'after').at(-1)!.fn()
    await h.settle()
    // The gap, then the resync in a post of its own.
    expect(h.posts[4]!.events).toMatchObject([{ type: 'gap', dropped: 2 }])
    h.posts[4]!.release()
    await h.settle()
    expect(h.posts[5]!.events).toMatchObject([{ type: 'resync', streaming: [{ ...tag, upTo: 1, blocks: [{ index: 0, kind: 'text', text: 'AB', upTo: 1 }] }] }])
    h.posts[5]!.release()
    await gen.next() // C follows the resync
    await h.settle()
    expect(h.posts[6]!.events).toMatchObject([{ type: 'chunk', ...tag, chunkIndex: 2, chunk: { text: 'C' } }])
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
        expect(h.posts.slice(-2).map((p) => p.events.map((e) => e.type))).toEqual([['session'], ['resync']])
        expect(h.posts.at(-1)!.events[0]).toMatchObject({
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
    // The owner's words under the steer's own first line: the row says it is a steer.
    expect(STEER_LINE).toBe('[sminos steer from human]')
    expect(h.calls[0]).toEqual({ op: 'append', args: { message: { type: 'user', content: [{ type: 'text', text: '[sminos steer from human]\nalso print the date' }] } } })
    // The mirror carries the words alone.
    expect(h.logs).toContain('steer: also print the date')
  })

  test("a steer whose text is the interrupt's marker or one of the bridge's notes goes in as a steer: its first line keeps the row from reading as either", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const moved = 'Task b1, the Bash command the interrupt moved to the background, was then stopped: it is not running, and no notification will come for it.'
    const texts = ['[Request interrupted by user]', '[Request interrupted by user from the desk]\nTask x was then stopped', stopNote('b1', 'desk'), `The interrupt came from the desk.\n${moved}`]
    for (const text of texts) {
      expect(await h.command({ op: 'steer', text })).toMatchObject({ ok: true })
    }
    const appended = h.calls.filter((c) => c.op === 'append').map((c) => (c.args as { message: { content: { text: string }[] } }).message.content[0]!.text)
    expect(appended).toEqual(texts.map((text) => `${STEER_LINE}\n${text}`))
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
    expect(submits[0]!.text).toBe(wakeText('answer', [NOTE]))
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
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([wakeText('answer', [NOTE])])
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
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([wakeText('answer', [NOTE, NOTE])])
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
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([wakeText('answer', [NOTE, NOTE])])
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
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([wakeText('answer', [NOTE])])
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
    await h.complete('t1', 'aborted')
    const record = said(h.conversation)
    expect(record).toContain('stuck01')
    expect(record).toContain('may still be running')
    expect(record).not.toContain('is not running')
  })

  test("the interrupt leaves the model its record, read at the next request: Esc's marker in a row of its own, then a note: from the desk, and the Bash call it moved to the background stopped, not running", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    let finish: (text: string) => void = () => undefined
    const running = h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: 'tu1', command: 'python3 -c sleep' }, () => new Promise((resolve) => (finish = (text) => resolve({ text }))))
    await h.settle()
    const answered = h.command({ op: 'interrupt', from: 'desk' })
    await h.settle()
    finish('Command running in background with ID: b5y6zo7fe. Output is being written to: /tmp/o. You will be notified when it completes.')
    // The moved call's result goes back to the engine (which ends the turn on it) only once the record is in:
    // a turn queued behind this one takes its messages before it waits for any hook.
    const rowsWhenBack = Promise.resolve(running).then(() => h.conversation.length)
    expect(await rowsWhenBack).toBe(2)
    // What `sminos interrupt` and the desk read is unchanged.
    expect(await answered).toEqual(expect.objectContaining({ ok: true, result: { turnId: 't1', stopped: ['b5y6zo7fe'], running: [] } }))
    await h.complete('t1', 'aborted')
    await h.turn('t2')
    await h.step({ turnId: 't2', index: 0, model: 'm', messageCount: 4 }, [])
    const read = h.requests[h.requests.length - 1]!
    // The marker's row holds the marker alone, as Esc's does: a transcript's reader knows an interrupt by nothing else.
    expect(read).toEqual([
      { type: 'user', content: [{ type: 'text', text: '[Request interrupted by user]' }] },
      { type: 'user', content: [{ type: 'text', text: expect.stringMatching(/^The interrupt came from the desk\.\nTask b5y6zo7fe, .* was then stopped: it is not running/) }] },
    ])
    // The terminal draws no appended row: a transcript line mirrors both, on one line.
    expect(h.logs).toContain(`interrupt: ${said(read).split('\n').join(' ')}`)
    // Its rows are named on the stream, as every row the session keeps is.
    expect(h.ofType('row-seen').filter((e) => e.door === 'note').length).toBe(2)
  })

  test('an interrupt with nothing to stop still leaves the record; one not from the desk says it came from outside the terminal', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    expect(await h.command({ op: 'interrupt' })).toMatchObject({ ok: true, result: { turnId: 't1', stopped: [], running: [] } })
    await h.complete('t1', 'aborted')
    await h.turn('t2')
    await h.step({ turnId: 't2', index: 0, model: 'm', messageCount: 3 }, [])
    expect(said(h.requests[h.requests.length - 1]!)).toBe('[Request interrupted by user]\nThe interrupt came from outside the terminal.')
  })

  test('a marker a hook refused leaves no note after it: a note alone would read as no interrupt at all', async () => {
    const h = harness({ denyAppend: '[Request interrupted by user]' })
    await h.ready()
    await h.turn('t1')
    expect(await h.command({ op: 'interrupt', from: 'desk' })).toMatchObject({ ok: true, result: { turnId: 't1' } })
    expect(h.calls.filter((c) => c.op === 'append').length).toBe(1)
    expect(h.conversation).toEqual([])
    expect(h.logs.some((l) => l.startsWith('interrupt: '))).toBe(false)
  })

  test('a turn the bridge did not interrupt gets nothing extra: one that answered, and one aborted from the terminal', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: 'tu1', command: 'ls' }, async () => ({ text: 'a\nb' }))
    await h.complete('t1')
    await h.turn('t2')
    await h.complete('t2', 'aborted')
    await h.turn('t3')
    await h.step({ turnId: 't3', index: 0, model: 'm', messageCount: 6 }, [])
    expect(h.requests[h.requests.length - 1]).toEqual([])
    expect(h.calls.filter((c) => c.op === 'append')).toEqual([])
  })

  test('an abort the engine refuses records nothing, and the turn ends without waiting on it', async () => {
    const h = harness({ abortFails: true })
    await h.ready()
    await h.turn('t1')
    expect(await h.command({ op: 'interrupt', from: 'desk' })).toMatchObject({ ok: false })
    await h.complete('t1')
    expect(h.calls.filter((c) => c.op === 'append')).toEqual([])
  })

  test("a second interrupt of the same turn, which the engine refuses, leaves the first's record whole", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    let finish: (text: string) => void = () => undefined
    const running = h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: 'tu1', command: 'sleep' }, () => new Promise((resolve) => (finish = (text) => resolve({ text }))))
    await h.settle()
    const first = h.command({ op: 'interrupt', from: 'desk' })
    await h.settle()
    expect(await h.command({ op: 'interrupt', from: 'desk' })).toMatchObject({ ok: false, error: expect.stringContaining('already ending') })
    finish('Command running in background with ID: b5y6zo7fe. Output is being written to: /o')
    expect(await Promise.resolve(running).then(() => h.conversation.length)).toBe(2)
    expect(await first).toMatchObject({ ok: true, result: { turnId: 't1', stopped: ['b5y6zo7fe'], running: [] } })
    await h.complete('t1', 'aborted')
    expect(h.calls.filter((c) => c.op === 'append').length).toBe(2)
    const record = said(h.conversation)
    expect(record).toMatch(/^\[Request interrupted by user\]\nThe interrupt came from the desk\.\n/)
    expect(record).toContain('b5y6zo7fe')
  })

  test('a moved Bash call waits for the record at most INTERRUPT_HOLD_MS (a TaskStop that never answers)', async () => {
    const h = harness({ taskStopHangs: true })
    await h.ready()
    await h.turn('t1')
    let finish: (text: string) => void = () => undefined
    let isBack = false
    const running = Promise.resolve(
      h.hook('tool.call', { tool: 'Bash' })(h.engine, { tool: 'Bash', tool_use_id: 'tu1', command: 'sleep' }, () => new Promise((resolve) => (finish = (text) => resolve({ text })))),
    ).then(() => (isBack = true))
    await h.settle()
    void h.command({ op: 'interrupt', from: 'desk' }).catch(() => undefined)
    await h.settle()
    finish('Command running in background with ID: stuck01. Output is being written to: /o')
    await h.settle()
    expect(isBack).toBe(false)
    await h.fire(INTERRUPT_HOLD_MS)
    await running
    expect(isBack).toBe(true)
  })
})

/** The text of the user rows a conversation holds, as the model reads them. */
const said = (rows: { type: string; content: { type: string; text: string }[] }[]) =>
  rows
    .filter((r) => r.type === 'user')
    .flatMap((r) => r.content.map((b) => b.text))
    .join('\n')

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

describe('stop', () => {
  test("a background task stopped with TaskStop, idle or mid-turn, whoever started it: the main loop's or a subagent's", async () => {
    const h = harness()
    await h.ready()
    expect(await h.command({ op: 'stop', taskId: 'bsh01', from: 'desk' })).toMatchObject({ ok: true, result: { taskId: 'bsh01' } })
    await h.turn('t1')
    expect(await h.command({ op: 'stop', taskId: 'mon_02' })).toMatchObject({ ok: true, result: { taskId: 'mon_02' } })
    expect(h.calls.filter((c) => c.op === 'tool')).toEqual([
      { op: 'tool', args: { tool: 'TaskStop', task_id: 'bsh01' } },
      { op: 'tool', args: { tool: 'TaskStop', task_id: 'mon_02' } },
    ])
    expect(h.calls.some((c) => c.op === 'abort'), 'the turn runs on').toBe(false)
  })

  test('each stop leaves the model a note, the rows\' record that the task stopped: from the desk, or from outside the terminal', async () => {
    const h = harness()
    await h.ready()
    await h.command({ op: 'stop', taskId: 'bsh01', from: 'desk' })
    await h.command({ op: 'stop', taskId: 'mon_02' })
    const record = said(h.conversation)
    expect(record).toContain('Task bsh01, a background task, was stopped from the desk: it is not running.')
    expect(record).toContain('Task mon_02, a background task, was stopped from outside the terminal: it is not running.')
    expect(stopNote('bsh01', 'desk')).toBe('Task bsh01, a background task, was stopped from the desk: it is not running.')
  })

  test("the engine's refusal is the answer's error, in its words without the tool-error wrapping; no note", async () => {
    const h = harness({ taskStopFails: ['gone01'] })
    await h.ready()
    ;(h.engine as unknown as { tool: { call: (a: Record<string, unknown>) => Promise<unknown> } }).tool.call = async () => ({
      text: '<tool_use_error>Task gone01 is not running (status: completed)</tool_use_error>',
      isError: true,
    })
    expect(await h.command({ op: 'stop', taskId: 'gone01' })).toMatchObject({ ok: false, error: 'Task gone01 is not running (status: completed)' })
    expect(said(h.conversation)).not.toContain('gone01')
  })

  test("an agent's id or name is refused before any TaskStop, which would end the agent", async () => {
    const h = harness({ agents: [{ id: 'a1b2c3d4e5f6a7b8c', description: 'Find it', type: 'general-purpose', status: 'running', name: 'finder' }] })
    await h.ready()
    for (const taskId of ['a1b2c3d4e5f6a7b8c', 'finder']) {
      expect(await h.command({ op: 'stop', taskId })).toMatchObject({ ok: false, error: `${taskId} is an agent, not a background shell or monitor` })
    }
    expect(h.calls.filter((c) => c.op === 'tool')).toEqual([])
  })

  test('a task id that is none is refused before any TaskStop', async () => {
    const h = harness()
    await h.ready()
    for (const taskId of [undefined, '', 'a b', 'x'.repeat(65), 7]) {
      expect(await h.command({ op: 'stop', taskId })).toMatchObject({ ok: false, error: 'stop needs a task id' })
    }
    expect(h.calls.filter((c) => c.op === 'tool')).toEqual([])
  })
})

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

  test("a session's event is refused: a peer's words never enter as the human's", async () => {
    const h = harness()
    await h.ready()
    const key = { project: 'p1', writer: 'mac/5d000003-0000-4000-8000-0000000000c3', seq: 1 }
    expect(await h.command({ op: 'deliver', key, text: '[sminos chat p 5d000003:1 from peer → @you]\nhi' })).toMatchObject({ ok: false })
    expect(await h.command({ op: 'deliver', key: { writer: 'hub/0123456789abcdef0123456789abcdef', seq: 1 }, text: 'owner' }))
      .toMatchObject({ ok: true, result: { submitted: true } })
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => c.args)).toEqual([{ text: 'owner', asUser: true }])
    expect(h.ofType('delivered').map((e) => e.key)).toEqual([{ writer: 'hub/0123456789abcdef0123456789abcdef', seq: 1 }])
  })

  test("each project numbers a writer's events on its own: the mark is per project, and a key naming none is held to the bare mark", async () => {
    const h = harness()
    await h.ready()
    const p1 = { project: 'p1', writer: 'mac/s1', seq: 98 }
    const p2 = { project: 'p2', writer: 'mac/s1', seq: 98 }
    expect(await h.command({ op: 'deliver', key: p1, text: 'p1 98' })).toMatchObject({ result: { submitted: true } })
    expect(await h.command({ op: 'deliver', key: p2, text: 'p2 98' })).toMatchObject({ result: { submitted: true } })
    expect(await h.command({ op: 'deliver', key: { ...p2, seq: 6 }, text: 'p2 6' })).toMatchObject({ result: { duplicate: true } })
    expect(await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 6 }, text: 'bare 6' })).toMatchObject({ result: { submitted: true } })
    expect(await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 5 }, text: 'bare 5' })).toMatchObject({ result: { duplicate: true } })
    expect(await h.command({ op: 'deliver', key: { ...p1, project: '' }, text: 'x' })).toMatchObject({ ok: false })
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual(['p1 98', 'p2 98', 'bare 6'])
    expect(h.ofType('delivered').map((e) => [e.key, e.outcome])).toEqual([
      [p1, 'submitted'],
      [p2, 'submitted'],
      [{ ...p2, seq: 6 }, 'duplicate'],
      [{ writer: 'mac/s1', seq: 6 }, 'submitted'],
      [{ writer: 'mac/s1', seq: 5 }, 'duplicate'],
    ])
  })

  test("a hello's kept marks are honored as they come: a bare mark guards only keys naming no project, a scoped one only its project", async () => {
    const h = harness()
    await h.start()
    // #229: a bare mark a writer raised in one project, kept before keys named theirs.
    h.children[0]!.write(hello(SID, SOCK, { override: null, delivered: { 'mac/s1': 98, 'p1/mac/s2': 4 } }))
    await h.settle()
    expect(await h.command({ op: 'deliver', key: { project: 'p2', writer: 'mac/s1', seq: 6 }, text: 'p2 6' })).toMatchObject({ result: { submitted: true } })
    expect(await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 98 }, text: 'bare 98' })).toMatchObject({ result: { duplicate: true } })
    expect(await h.command({ op: 'deliver', key: { project: 'p1', writer: 'mac/s2', seq: 4 }, text: 'p1 4' })).toMatchObject({ result: { duplicate: true } })
    expect(await h.command({ op: 'deliver', key: { project: 'p3', writer: 'mac/s2', seq: 4 }, text: 'p3 4' })).toMatchObject({ result: { submitted: true } })
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual(['p2 6', 'p3 4'])
  })

  test("busy: the delivery goes into the running turn as a row, read at its next request; `submitted`, then `entered` with the row; mirrored; nothing submitted", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const key = { project: 'p1', writer: 'mac/s1', seq: 3 }
    const text = '[sminos chat p mac/s1:3 from peer → @you]\nthe build is green'
    expect(await h.command({ op: 'deliver', key, text })).toMatchObject({ ok: true, result: { submitted: true } })
    await h.settle()
    expect(h.calls).toEqual([{ op: 'append', args: { message: { type: 'user', content: [{ type: 'text', text }] } } }])
    expect(h.ofType('delivered').map((e) => [e.key, e.outcome, e.uuid])).toEqual([
      [key, 'submitted', undefined],
      [key, 'entered', 'row-1'],
    ])
    expect(h.logs).toContain('delivered: [sminos chat p mac/s1:3 from peer → @you] the build is green')
    // The next request carries it.
    await h.step({ turnId: 't1', index: 1, model: 'm', messageCount: 3 }, [])
    expect(h.requests.at(-1)!.map((m) => m.content[0]!.text)).toEqual([text])
  })

  test('busy: a turn that answers before any request read the delivered row wakes the session once; one a request read wakes nothing', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 1 }, text: 'unread' })
    await h.complete('t1')
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => c.args)).toEqual([{ text: wakeText('answer', [MESSAGE()]), asUser: true }])
    await h.turn('t2')
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 2 }, text: 'read' })
    await h.step({ turnId: 't2', index: 1, model: 'm', messageCount: 3 }, [])
    await h.complete('t2')
    expect(h.calls.filter((c) => c.op === 'submit').length).toBe(1)
  })

  test('busy: an append the engine refuses is `refused` with the key whole, and wakes nothing', async () => {
    const h = harness({ denyAppend: 'blocked' })
    await h.ready()
    await h.turn('t1')
    const key = { project: 'p1', writer: 'mac/s1', seq: 4 }
    expect(await h.command({ op: 'deliver', key, text: 'blocked' })).toMatchObject({ ok: true, result: { submitted: true } })
    await h.settle()
    await h.complete('t1')
    expect(h.ofType('delivered').map((e) => [e.key, e.outcome, e.reason])).toEqual([
      [key, 'submitted', undefined],
      [key, 'refused', 'refused by a hook'],
    ])
    expect(h.calls.filter((c) => c.op === 'submit')).toEqual([])
  })

  test("a delivered row an Esc rewound past (the prompt handed back, the next one sent where it stood) goes in again as the next turn starts, named `entered` again", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const key = { writer: 'mac/s1', seq: 5 }
    await h.command({ op: 'deliver', key, text: 'the delivered words' })
    await h.complete('t1', 'aborted')
    expect(h.calls.filter((c) => c.op === 'submit')).toEqual([])
    h.setApiConversation([{ role: 'user', content: [{ type: 'text', text: 'the prompt, edited' }] }])
    await h.turn('t2')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'append').length).toBe(2)
    expect(h.ofType('delivered').map((e) => [e.outcome, e.uuid])).toEqual([
      ['submitted', undefined],
      ['entered', 'row-1'],
      ['entered', 'row-2'],
    ])
    // Given in t2, it is t2's: a turn that answers lets it go, and the next turn reads nothing.
    await h.step({ turnId: 't2', index: 1, model: 'm', messageCount: 3 }, [])
    await h.complete('t2')
    const reads = h.apiReads()
    await h.turn('t3')
    await h.settle()
    expect(h.apiReads()).toBe(reads)
    expect(h.calls.filter((c) => c.op === 'append').length).toBe(2)
  })

  test("a row given again as a turn starts is not in that turn's first request: a turn that answers in one request wakes once", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 8 }, text: 'given again' })
    await h.complete('t1', 'aborted')
    h.setApiConversation([])
    await h.turn('t2')
    await h.settle()
    // The first request was built as the turn began, before the row went in.
    await h.step({ turnId: 't2', index: 0, model: 'm', messageCount: 2 }, [])
    await h.complete('t2')
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([wakeText('answer', [MESSAGE()])])
  })

  test('a delivered row an interrupted turn kept (Esc mid-tool) is let go at the next turn, not given again', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 6 }, text: 'kept words' })
    await h.complete('t1', 'aborted')
    h.setApiConversation([{ role: 'user', content: [{ type: 'text', text: 'prompt' }, { type: 'text', text: 'kept words' }] }, { role: 'user', content: 'next' }])
    await h.turn('t2')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'append').length).toBe(1)
    await h.complete('t2', 'aborted')
    await h.turn('t3')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'append').length).toBe(1)
    // t1's end checked it before its wake; t2's start let it go.
    expect(h.apiReads()).toBe(2)
  })

  test("idle: a prompt the engine refuses because the human stopped the session goes in as the busy path's row, and only the bridge's wake goes to the inbox: `submitted`, then `entered`; the key kept", async () => {
    for (const drop of ['the session was stopped and nobody has sent input since', 'the prompt was removed from the queue before it ran']) {
      const h = harness({ submitDrops: drop })
      await h.ready()
      const key = { project: 'p1', writer: 'mac/human', seq: 7 }
      const text = '[sminos chat p human:7 from human → @you]\nyes, go ahead'
      expect(await h.command({ op: 'deliver', key, text })).toMatchObject({ ok: true, result: { submitted: true } })
      await h.settle()
      expect([drop, h.calls]).toEqual([
        drop,
        [
          { op: 'submit', args: { text, asUser: true } },
          { op: 'append', args: { message: { type: 'user', content: [{ type: 'text', text }] } } },
        ],
      ])
      expect(h.ofType('delivered').map((e) => [e.key, e.outcome, e.uuid])).toEqual([
        [key, 'submitted', undefined],
        [key, 'entered', 'row-2'],
      ])
      // The human's words go in the conversation, never through the inbox, which the engine delivers as a peer's.
      expect(h.ofType('inbox').map((e) => [e.text, e.key])).toEqual([[wakeText('stopped', [MESSAGE('[sminos chat p human:7 from human → @you]')]), undefined]])
      expect(h.logs).toContain('delivered: [sminos chat p human:7 from human → @you] yes, go ahead')
      expect(await h.command({ op: 'deliver', key, text })).toMatchObject({ ok: true, result: { duplicate: true } })
      expect(h.calls.length).toBe(2)
    }
  })

  test('idle: a row given after a stop is checked as the next turn starts: one the conversation lacks goes in again, one it holds is let go', async () => {
    for (const isHeld of [false, true]) {
      const h = harness({ submitDrops: 'the session was stopped and nobody has sent input since' })
      await h.ready()
      await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 1 }, text: 'words after the Esc' })
      await h.settle()
      if (!isHeld) {
        h.setApiConversation([{ role: 'user', content: [{ type: 'text', text: 'a prompt sent where an earlier one stood' }] }])
      }
      // The turn the wake (or the human) starts.
      await h.turn('t1')
      await h.settle()
      expect([isHeld, h.apiReads(), h.calls.filter((c) => c.op === 'append').length]).toEqual([isHeld, 1, isHeld ? 1 : 2])
      expect([isHeld, h.ofType('delivered').map((e) => e.outcome)]).toEqual([isHeld, isHeld ? ['submitted', 'entered'] : ['submitted', 'entered', 'entered']])
      await h.step({ turnId: 't1', index: 1, model: 'm', messageCount: 3 }, [])
      await h.complete('t1')
      await h.turn('t2')
      await h.settle()
      expect([isHeld, h.apiReads()]).toEqual([isHeld, 1])
    }
  })

  test('idle: a stop that drops a prompt after it was taken (an Esc emptied the queue it waited in) puts it in as a row: woken through the inbox when no turn runs; bound to the turn the Esc is still ending, woken by its end', async () => {
    for (const isTurnEnding of [false, true]) {
      const h = harness({ holdSubmit: true })
      await h.ready()
      const key = { project: 'p1', writer: 'mac/human', seq: 2 }
      expect(await h.command({ op: 'deliver', key, text: 'queued words' })).toMatchObject({ ok: true, result: { submitted: true } })
      if (isTurnEnding) {
        await h.turn('t1')
      }
      h.submits[0]!({ drop: 'the prompt was removed from the queue before it ran' })
      await h.settle()
      expect([isTurnEnding, h.calls.filter((c) => c.op === 'append').length, h.ofType('delivered').map((e) => e.outcome)]).toEqual([isTurnEnding, 1, ['submitted', 'entered']])
      expect([isTurnEnding, h.ofType('inbox').length]).toEqual([isTurnEnding, isTurnEnding ? 0 : 1])
      if (isTurnEnding) {
        await h.complete('t1', 'aborted')
      }
      expect([isTurnEnding, h.ofType('inbox').map((e) => [e.text, e.key])]).toEqual([isTurnEnding, [[wakeText(isTurnEnding ? 'aborted' : 'stopped', [MESSAGE()]), undefined]]])
      expect(h.calls.filter((c) => c.op === 'submit').length).toBe(1)
    }
  })

  test('idle: a row a stop sent in that the engine refuses is `refused`, and wakes nothing; one still pending through a /clear wakes nothing in the new conversation', async () => {
    const refused = harness({ submitDrops: 'the session was stopped and nobody has sent input since', denyAppend: 'blocked words' })
    await refused.ready()
    const key = { project: 'p1', writer: 'mac/human', seq: 3 }
    expect(await refused.command({ op: 'deliver', key, text: 'blocked words' })).toMatchObject({ ok: true, result: { submitted: true } })
    await refused.settle()
    expect(refused.ofType('delivered').map((e) => [e.key, e.outcome, e.reason])).toEqual([
      [key, 'submitted', undefined],
      [key, 'refused', 'refused by a hook'],
    ])
    expect(refused.ofType('inbox')).toEqual([])
    const h = harness({ submitDrops: 'the session was stopped and nobody has sent input since', holdAppend: true })
    await h.ready()
    await h.command({ op: 'deliver', key, text: 'old words' })
    await h.hook('session.end', {})(h.engine, { reason: 'clear', sessionId: SID }, async () => ({}))
    await h.settle()
    const NEW = '6c000003-0000-4000-8000-00000000006c'
    const NEWSOCK = `/tmp/s/bridge/${NEW}.sock`
    h.setSession(NEW)
    h.timers.filter((t) => t.kind === 'after').at(-1)!.fn()
    await h.settle()
    h.children[1]!.write(hello(NEW, NEWSOCK))
    await h.settle()
    h.appends.shift()!()
    await h.settle()
    expect(h.posts.filter((p) => p.socketPath === NEWSOCK).length).toBeGreaterThan(0)
    expect(h.ofType('inbox')).toEqual([])
  })

  test('idle: a main turn that starts while a row a stop sent in is still pending takes it as a busy delivery: no wake at once; its end wakes the session only if no request of it read the row', async () => {
    for (const isRead of [false, true]) {
      const h = harness({ submitDrops: 'the session was stopped and nobody has sent input since', holdAppend: true })
      await h.ready()
      await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 1 }, text: '[sminos message from human id=m1]\nwords' })
      await h.turn('t1')
      h.appends.shift()!()
      await h.settle()
      expect([isRead, h.ofType('delivered').map((e) => e.outcome), h.ofType('inbox')]).toEqual([isRead, ['submitted', 'entered'], []])
      if (isRead) {
        await h.step({ turnId: 't1', index: 1, model: 'm', messageCount: 3 }, [])
      }
      await h.complete('t1', 'aborted')
      expect([isRead, h.ofType('inbox').map((e) => e.text)]).toEqual([isRead, isRead ? [] : [wakeText('aborted', [MESSAGE('[sminos message from human id=m1]')])]])
    }
  })

  test("a wake says what is unread and where: a message for you, a note, or both, as many as there are, when they went in; then the messages' frame lines", async () => {
    expect(wakeText('answer', [NOTE])).toBe(
      '[sminos bridge]\nA note was added to the conversation while you were finishing your answer, too late for that answer to take it in. It is the user message just before your last answer: read it and act on it now.',
    )
    expect(wakeText('answer', [MESSAGE('[sminos message from human id=m1]')])).toBe(
      '[sminos bridge]\nA message for you was added to the conversation while you were finishing your answer, too late for that answer to take it in. It is the user message just before your last answer: read it and act on it now.\nUnread: [sminos message from human id=m1]',
    )
    expect(wakeText('answer', [NOTE, MESSAGE('[sminos message from human id=m1]')])).toBe(
      '[sminos bridge]\nA message for you and a note were added to the conversation while you were finishing your answer, too late for that answer to take them in. They are the user messages just before your last answer: read them and act on them now.\nUnread: [sminos message from human id=m1]',
    )
    expect(wakeText('aborted', [MESSAGE('[sminos message from human id=m1]'), MESSAGE('[sminos message from human id=m2]'), NOTE, NOTE])).toBe(
      '[sminos bridge]\n2 messages for you and 2 notes were added to the conversation during your turn, which was stopped before you read them. They are the user messages before this message: read them and act on them now.\nUnread: [sminos message from human id=m1] [sminos message from human id=m2]',
    )
    expect(wakeText('stopped', [MESSAGE('[sminos message from human id=m1]')])).toBe(
      '[sminos bridge]\nA message for you was added to the conversation after your turn was stopped. It is the user message before this message: read it and act on it now.\nUnread: [sminos message from human id=m1]',
    )
  })

  test('one wake for a turn that ended with a steer and a delivered message both unread names both: answered (prompt and inbox alike) or stopped', async () => {
    const h = harness({ submitDrops: 'the session was stopped and nobody has sent input since' })
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'steer', text: 'mind the tests' })
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 1 }, text: '[sminos message from human id=m1]\nship it' })
    await h.complete('t1')
    await h.settle()
    const both =
      '[sminos bridge]\nA message for you and a note were added to the conversation while you were finishing your answer, too late for that answer to take them in. They are the user messages just before your last answer: read them and act on them now.\nUnread: [sminos message from human id=m1]'
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([both])
    expect(h.ofType('inbox').map((e) => e.text)).toEqual([both])
    await h.turn('t2')
    await h.settle()
    await h.command({ op: 'steer', text: 'and the docs' })
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 2 }, text: '[sminos message from human id=m2]\nthen merge' })
    await h.complete('t2', 'aborted')
    expect(h.ofType('inbox').map((e) => e.text).at(-1)).toBe(
      '[sminos bridge]\nA message for you and a note were added to the conversation during your turn, which was stopped before you read them. They are the user messages before this message: read them and act on them now.\nUnread: [sminos message from human id=m2]',
    )
  })

  test("a stopped turn's check and the next turn's never take one row both: a row the next turn's check holds is not given again by the stopped turn's, whose wake comes late (an append still pending at its end)", async () => {
    const options: NonNullable<Parameters<typeof harness>[0]> = { holdAppend: true }
    const h = harness(options)
    await h.ready()
    await h.turn('t1')
    const first = '[sminos message from human id=m1]\nfirst words'
    const second = '[sminos message from human id=m2]\nsecond words'
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 1 }, text: first })
    h.appends.shift()!()
    await h.settle()
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 2 }, text: second })
    // The turn is stopped with the second append still pending: its wake waits for it.
    await h.complete('t1', 'aborted')
    h.setApiConversation([{ role: 'user', content: [{ type: 'text', text: second }] }])
    const release = h.holdApiReads()
    // The next turn's check takes the first row and waits on the conversation.
    await h.turn('t2')
    await h.settle()
    // The second append lands: the stopped turn's check starts, and waits too.
    h.appends.shift()!()
    await h.settle()
    options.holdAppend = false
    release()
    await h.settle()
    const appended = h.calls.filter((c) => c.op === 'append').map((c) => JSON.stringify(c.args))
    expect(appended.filter((a) => a.includes('first words')).length).toBe(2)
    expect(appended.filter((a) => a.includes('second words')).length).toBe(1)
  })

  test('a compaction while a check of delivered rows reads the conversation gives no row again: the summary carries them (the stopped turn\'s check, and the next turn\'s)', async () => {
    const compact = (h: ReturnType<typeof harness>) => h.hook('session.compact', { trigger: 'auto' })(h.engine, { messages: [], trigger: 'auto' }, async () => ({ messages: [] }))
    const words = '[sminos message from human id=m1]\nhandled words'
    // What the check's read answers: the row gone, or (a read before the compaction) still there.
    const cases = [
      ['the stopped turn', []],
      ['the stopped turn', [{ role: 'user', content: [{ type: 'text', text: words }] }]],
      ['the next turn', []],
    ] as const
    for (const [at, read] of cases) {
      const h = harness()
      await h.ready()
      await h.turn('t1')
      await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 1 }, text: words })
      if (at === 'the next turn') {
        await h.complete('t1', 'aborted')
        await h.settle()
      }
      h.setApiConversation([...read])
      const release = h.holdApiReads()
      if (at === 'the stopped turn') {
        await h.complete('t1', 'aborted')
      } else {
        await h.turn('t2')
      }
      await h.settle()
      await compact(h)
      release()
      await h.settle()
      expect([at, read.length, h.calls.filter((c) => c.op === 'append').length]).toEqual([at, read.length, 1])
      // Nor at a later turn's check, which reads the summary (no row verbatim).
      h.setApiConversation([])
      await h.turn('t3')
      await h.settle()
      expect([at, read.length, h.calls.filter((c) => c.op === 'append').length]).toEqual([at, read.length, 1])
    }
  })

  test("a stopped turn whose Esc rewound its delivered row: the row goes in again before any wake, which names it as given after the stop; a row it still holds is named in the stopped turn's wake", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 1 }, text: '[sminos message from human id=m1]\nrewound words' })
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 2 }, text: '[sminos message from human id=m2]\nheld words' })
    // The Esc came before the model answered: the conversation lost the first row with the prompt.
    h.setApiConversation([{ role: 'user', content: [{ type: 'text', text: '[sminos message from human id=m2]\nheld words' }] }])
    await h.complete('t1', 'aborted')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'append').map((c) => JSON.stringify(c.args))).toEqual([
      expect.stringContaining('rewound words'),
      expect.stringContaining('held words'),
      expect.stringContaining('rewound words'),
    ])
    expect(h.ofType('inbox').map((e) => e.text)).toEqual([
      wakeText('aborted', [MESSAGE('[sminos message from human id=m2]')]),
      wakeText('stopped', [MESSAGE('[sminos message from human id=m1]')]),
    ])
    // The row given again is checked at the next turn, and is not given a third time.
    h.setApiConversation(undefined)
    await h.turn('t2')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'append').length).toBe(3)
  })

  test("every inbox wake names the delivered rows it points at by their frame lines, so no two are one text (the engine drops a peer message identical to its sender's last within 30 s); a text with no frame line is never quoted", async () => {
    const h = harness({ submitDrops: 'the session was stopped and nobody has sent input since' })
    await h.ready()
    const framed = (seq: number) => `[sminos message from human id=m${seq}]\nthe human's words ${seq}`
    // Two messages after one Esc, the second while the first's wake has been sent.
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 1 }, text: framed(1) })
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 2 }, text: framed(2) })
    // A stopped turn that left three rows unread, two of them texts that open with no frame line.
    await h.turn('t1')
    await h.settle()
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 3 }, text: framed(3) })
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 4 }, text: 'one line of the human' })
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 5 }, text: "[the human's first line]\nand the next" })
    await h.complete('t1', 'aborted')
    // A turn that answered before reading a row, whose wake prompt the stop refuses.
    await h.turn('t2')
    await h.settle()
    await h.command({ op: 'deliver', key: { writer: 'mac/human', seq: 6 }, text: framed(6) })
    await h.complete('t2')
    await h.settle()
    const wakes = h.ofType('inbox').map((e) => e.text as string)
    expect(wakes).toEqual([
      wakeText('stopped', [MESSAGE('[sminos message from human id=m1]')]),
      wakeText('stopped', [MESSAGE('[sminos message from human id=m2]')]),
      wakeText('aborted', [MESSAGE('[sminos message from human id=m3]'), MESSAGE(), MESSAGE()]),
      wakeText('answer', [MESSAGE('[sminos message from human id=m6]')]),
    ])
    expect(wakes.filter((w) => w.includes("the human's") || w.includes('one line of the human'))).toEqual([])
  })

  test('a delivered row a stopped turn left unread wakes the session once through its inbox (the engine refuses the prompt then); one a request read, or a steer, wakes nothing', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 1 }, text: 'unread one' })
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 2 }, text: 'unread two' })
    await h.complete('t1', 'aborted')
    expect(h.ofType('inbox').map((e) => [e.text, e.key])).toEqual([[wakeText('aborted', [MESSAGE(), MESSAGE()]), undefined]])
    expect(h.calls.filter((c) => c.op === 'submit')).toEqual([])
    // The rows held, the next turn lets them go; it reads a new one before its Esc.
    await h.turn('t2')
    await h.settle()
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 3 }, text: 'read' })
    await h.step({ turnId: 't2', index: 1, model: 'm', messageCount: 4 }, [])
    await h.complete('t2', 'aborted')
    await h.turn('t3')
    await h.settle()
    await h.command({ op: 'steer', text: 'a steer, unread' })
    await h.complete('t3', 'aborted')
    expect(h.ofType('inbox').length).toBe(1)
  })

  test("a turn that answers before reading a delivered row, whose wake the engine refuses for a stop, wakes the session through its inbox; a steer's alone does not", async () => {
    const h = harness({ submitDrops: 'the session was stopped and nobody has sent input since' })
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'steer', text: 'steer only' })
    await h.complete('t1')
    await h.settle()
    expect(h.ofType('inbox')).toEqual([])
    await h.turn('t2')
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 1 }, text: 'delivered, unread' })
    await h.complete('t2')
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)).toEqual([wakeText('answer', [NOTE]), wakeText('answer', [MESSAGE()])])
    expect(h.ofType('inbox').map((e) => e.text)).toEqual([wakeText('answer', [MESSAGE()])])
  })

  test("a wake queued behind the human's prompt, whose turn read the delivered row before an Esc emptied the queue, sends no inbox frame; one no request read since still does", async () => {
    for (const [isReadMeanwhile, frames] of [
      [true, 0],
      [false, 1],
    ] as const) {
      const h = harness({ holdSubmit: true })
      await h.ready()
      await h.turn('t1')
      await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 1 }, text: 'delivered, unread' })
      await h.complete('t1')
      expect(h.submits.length).toBe(1)
      // The human's prompt runs ahead of the wake; its first request carries the row.
      await h.turn('t2')
      if (isReadMeanwhile) {
        await h.step({ turnId: 't2', index: 0, model: 'm', messageCount: 3 }, [])
      }
      await h.complete('t2', 'aborted')
      h.submits[0]!({ drop: 'the prompt was removed from the queue before it ran' })
      await h.settle()
      expect([isReadMeanwhile, h.ofType('inbox').length]).toEqual([isReadMeanwhile, frames])
    }
  })

  test("a delivery whose append is still pending through an Esc and a /clear wakes nothing when it lands: its turn was the old conversation's", async () => {
    const h = harness({ holdAppend: true })
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 1 }, text: 'old words' })
    await h.complete('t1', 'aborted')
    await h.hook('session.end', {})(h.engine, { reason: 'clear', sessionId: SID }, async () => ({}))
    await h.settle()
    const NEW = '6c000002-0000-4000-8000-00000000006c'
    const NEWSOCK = `/tmp/s/bridge/${NEW}.sock`
    h.setSession(NEW)
    h.timers.filter((t) => t.kind === 'after').at(-1)!.fn()
    await h.settle()
    h.children[1]!.write(hello(NEW, NEWSOCK))
    await h.settle()
    h.appends.shift()!()
    await h.settle()
    expect(h.posts.filter((p) => p.socketPath === NEWSOCK).length).toBeGreaterThan(0)
    expect(h.ofType('inbox')).toEqual([])
    expect(h.calls.filter((c) => c.op === 'submit')).toEqual([])
  })

  test("a compaction lets every delivered row go: one read before an Esc, its words now only in the summary, is not given again (the bridge's own compaction, and the engine's)", async () => {
    const compactions: [string, (h: ReturnType<typeof harness>) => Promise<unknown>][] = [
      [
        'compact command',
        async (h) => {
          await h.command({ op: 'compact' })
          h.compactions[0]!.finish({ messages: [], tokensBefore: 9, tokensAfter: 1 })
        },
      ],
      ['session.compact', async (h) => h.hook('session.compact', { trigger: 'auto' })(h.engine, { messages: [], trigger: 'auto' }, async () => ({ messages: [] }))],
    ]
    for (const [way, compactNow] of compactions) {
      const h = harness()
      await h.ready()
      await h.turn('t1')
      await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 9 }, text: 'read, then compacted' })
      await h.step({ turnId: 't1', index: 1, model: 'm', messageCount: 3 }, [])
      await h.complete('t1', 'aborted')
      await compactNow(h)
      await h.settle()
      h.setApiConversation([{ role: 'user', content: [{ type: 'text', text: 'This session is being continued from a previous conversation…' }] }])
      await h.turn('t2')
      await h.settle()
      expect([way, h.calls.filter((c) => c.op === 'append').length, h.apiReads()]).toEqual([way, 1, 0])
    }
  })

  test("rows given again as a turn starts are each bound to it before the check's first await: a one-request turn that ends while the first replay is pending still wakes once for the second", async () => {
    const options: NonNullable<Parameters<typeof harness>[0]> = { holdAppend: true }
    const h = harness(options)
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 1 }, text: 'first words' })
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 2 }, text: 'second words' })
    for (const release of h.appends.splice(0)) {
      release()
    }
    await h.settle()
    await h.complete('t1', 'aborted')
    h.setApiConversation([])
    // The first replay is refused, so only the second can owe the wake.
    options.denyAppend = 'first words'
    await h.turn('t2')
    await h.settle()
    await h.step({ turnId: 't2', index: 0, model: 'm', messageCount: 2 }, [])
    await h.complete('t2')
    const wakes = () => h.calls.filter((c) => c.op === 'submit').map((c) => (c.args as { text: string }).text)
    h.appends.shift()!()
    await h.settle()
    expect(wakes()).toEqual([])
    h.appends.shift()!()
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'append').length).toBe(4)
    expect(wakes()).toEqual([wakeText('answer', [MESSAGE()])])
  })

  test('a /clear while the re-check reads the conversation: nothing of the old conversation is given again, nor kept to be checked in the new one', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.command({ op: 'deliver', key: { writer: 'mac/s1', seq: 1 }, text: 'old words' })
    await h.complete('t1', 'aborted')
    h.setApiConversation([])
    const release = h.holdApiReads()
    await h.turn('t2')
    await h.settle()
    // t1's end checked it before its wake (held then); t2's start checks it again.
    expect(h.apiReads()).toBe(2)
    await h.complete('t2', 'aborted')
    await h.hook('session.end', {})(h.engine, { reason: 'clear', sessionId: SID }, async () => ({}))
    release()
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'append').length).toBe(1)
    await h.turn('t3')
    await h.settle()
    expect(h.apiReads()).toBe(2)
    expect(h.calls.filter((c) => c.op === 'submit')).toEqual([])
  })

  test('a deliver with no key or no text is refused', async () => {
    const h = harness()
    await h.ready()
    expect(await h.command({ op: 'deliver', text: 'x' })).toMatchObject({ ok: false })
    expect(await h.command({ op: 'deliver', key: { writer: 'w', seq: 1 } })).toMatchObject({ ok: false })
    expect(h.calls.length).toBe(0)
  })
})

describe("a delivered prompt's row (G6)", () => {
  const ORIGIN = { kind: 'plugin', name: PLUGIN, asUser: true }
  const promptRow = (text: string, uuid: string, origin: Record<string, unknown> = ORIGIN, agentId?: string) => ({
    door: 'prompt',
    message: { type: 'user', role: 'user', content: [{ type: 'text', text }] },
    extra: { uuid, origin, ...(agentId !== undefined && { agentId }) },
  })

  test('the row this plugin submitted as the human words is named once it is kept: `entered` with its uuid', async () => {
    const h = harness()
    await h.ready()
    const key = { writer: 'hub/m1', seq: 3 }
    const text = '[sminos chat p hub/m1:3 from human → @you]\nship it'
    await h.command({ op: 'deliver', key, text })
    const r = promptRow(text, 'row-entered')
    await h.append(r.door, r.message, r.extra)
    expect(h.ofType('delivered').map((e) => [e.key, e.outcome, e.uuid])).toEqual([
      [key, 'submitted', undefined],
      [key, 'entered', 'row-entered'],
    ])
    // Named once: the same text kept again (a later row) names nothing.
    const again = promptRow(text, 'row-later')
    await h.append(again.door, again.message, again.extra)
    expect(h.ofType('delivered').length).toBe(2)
  })

  test('a context block beside the prompt (the ask mod) does not hide it: the first text block is the prompt', async () => {
    const h = harness()
    await h.ready()
    const key = { writer: 'hub/m1', seq: 4 }
    await h.command({ op: 'deliver', key, text: 'frame\nhello' })
    await h.append(
      'prompt',
      { type: 'user', role: 'user', content: [{ type: 'text', text: 'frame\nhello' }, { type: 'text', text: 'an answer the ask mod held' }] },
      { uuid: 'row-c', origin: ORIGIN },
    )
    expect(h.ofType('delivered').at(-1)).toMatchObject({ key, outcome: 'entered', uuid: 'row-c' })
  })

  test('no guessing: a typed prompt of the same text, another origin, a subagent row, or a rewritten text names nothing', async () => {
    const h = harness()
    await h.ready()
    await h.command({ op: 'deliver', key: { writer: 'hub/m1', seq: 5 }, text: 'continue' })
    for (const r of [
      promptRow('continue', 'typed', { kind: 'composer' }),
      promptRow('continue', 'other-plugin', { kind: 'plugin', name: 'other', asUser: true }),
      promptRow('continue', 'framed', { kind: 'plugin', name: PLUGIN }),
      promptRow('continue', 'in-a-subagent', ORIGIN, 'a1'),
      promptRow('continue, rewritten', 'rewritten'),
    ]) {
      await h.append(r.door, r.message, r.extra)
    }
    await h.append('note', { type: 'user', role: 'user', content: [{ type: 'text', text: 'continue' }] }, { uuid: 'a-note', origin: ORIGIN })
    expect(h.ofType('delivered').map((e) => e.outcome)).toEqual(['submitted'])
  })

  test('two submissions still waiting with the same text: neither is named', async () => {
    const h = harness()
    await h.ready()
    await h.command({ op: 'deliver', key: { writer: 'hub/m1', seq: 6 }, text: 'same' })
    await h.command({ op: 'deliver', key: { writer: 'hub/m2', seq: 1 }, text: 'same' })
    const r = promptRow('same', 'row-same')
    await h.append(r.door, r.message, r.extra)
    expect(h.ofType('delivered').map((e) => e.outcome)).toEqual(['submitted', 'submitted'])
  })

  test('a submission the engine dropped is refused with its reason, and no later row is taken for it', async () => {
    const h = harness({ submitDrops: 'a Stop hook stands' })
    await h.ready()
    const key = { writer: 'hub/m1', seq: 7 }
    await h.command({ op: 'deliver', key, text: 'dropped' })
    await h.settle()
    const r = promptRow('dropped', 'row-d')
    await h.append(r.door, r.message, r.extra)
    expect(h.ofType('delivered').map((e) => [e.outcome, e.reason])).toEqual([
      ['submitted', undefined],
      ['refused', 'a Stop hook stands'],
    ])
  })

  /** Releases the posts after the first in order until one carries a refusal; that post is left held. */
  const untilRefusal = async (h: ReturnType<typeof harness>) => {
    const isRefusal = (e: Record<string, unknown>) => e.type === 'delivered' && e.outcome === 'refused'
    for (let i = 1; !h.posts.slice(0, i + 1).some((p) => p.events.some(isRefusal)); i++) {
      h.posts[i]!.release()
      await h.settle()
    }
    return h.posts.find((p) => p.events.some(isRefusal))!
  }
  /** The poster's retry after a failed post: the gap it posts, answered, then the resync in a post of its own. */
  const retry = async (h: ReturnType<typeof harness>) => {
    h.timers.filter((t) => t.kind === 'after').at(-1)!.fn()
    await h.settle()
    const gap = h.posts.at(-1)!
    gap.release()
    await h.settle()
    return { gap, resync: h.posts.at(-1)! }
  }

  test('a refusal whose post is lost rides every resync, with its reason, until a post that carried it is answered', async () => {
    const h = harness({ hold: true, submitDrops: 'a Stop hook stands' })
    await h.start()
    h.children[0]!.write(hello())
    await h.settle()
    h.posts[0]!.release()
    await h.settle()
    const key = { project: 'p1', writer: 'hub/m1', seq: 8 }
    h.children[0]!.write(line({ id: 'c1', op: 'deliver', key, text: 'dropped' }))
    await h.settle()
    ;(await untilRefusal(h)).fail() // the refusal never reaches the child
    await h.settle()
    let recovery = await retry(h)
    expect([recovery.gap, recovery.resync].map((p) => p.events.map((e) => e.type))).toEqual([['gap'], ['resync']])
    expect(recovery.resync.events[0]!.refused).toEqual([{ key, reason: 'a Stop hook stands' }])
    recovery.resync.fail() // nor does the resync that carried it
    await h.settle()
    recovery = await retry(h)
    expect(recovery.resync.events[0]!.refused).toEqual([{ key, reason: 'a Stop hook stands' }])
    recovery.resync.release() // the child has it now
    await h.settle()
    await h.turn('t9')
    await h.settle()
    h.posts.at(-1)!.fail()
    await h.settle()
    recovery = await retry(h)
    expect(recovery.resync.events[0]).toMatchObject({ type: 'resync', refused: [] })
  })

  test('a refusal whose own post was answered is not carried by a later resync', async () => {
    const h = harness({ hold: true, submitDrops: 'a Stop hook stands' })
    await h.start()
    h.children[0]!.write(hello())
    await h.settle()
    h.posts[0]!.release()
    await h.settle()
    h.children[0]!.write(line({ id: 'c1', op: 'deliver', key: { writer: 'hub/m1', seq: 9 }, text: 'dropped' }))
    await h.settle()
    ;(await untilRefusal(h)).release()
    await h.settle()
    await h.turn('t9')
    await h.settle()
    h.posts.at(-1)!.fail()
    await h.settle()
    expect((await retry(h)).resync.events[0]).toMatchObject({ type: 'resync', refused: [] })
  })
})

describe('agents the module did not see spawn ($.agent.list())', () => {
  const listed = (id: string, status: string, extra: Record<string, unknown> = {}) => ({ id, description: `task ${id}`, type: 'general-purpose', status, ...extra })

  test('at load the agent state is seeded from the list, so the first resync carries every agent with what the list gives and no more', async () => {
    const h = harness({
      messages: [{}],
      agents: [
        listed('a1', 'running', { name: 'scout' }),
        listed('a2', 'completed'),
        listed('a3', 'idle', { parentId: 'a1' }),
        listed('a4', 'killed'),
        listed('a5', 'waiting', { spawnedBy: 'other', teammateId: 'x@t' }),
      ],
    })
    await h.ready()
    expect(h.events().map((e) => e.type)).toEqual(['session', 'resync'])
    expect(h.events()[1]!.agents).toEqual([
      { agentId: 'a1', parentAgentId: null, subagentType: 'general-purpose', description: 'task a1', name: 'scout', running: true },
      { agentId: 'a2', parentAgentId: null, subagentType: 'general-purpose', description: 'task a2', agentType: 'general-purpose', running: false },
      { agentId: 'a3', parentAgentId: 'a1', subagentType: 'general-purpose', description: 'task a3', running: true },
      { agentId: 'a4', parentAgentId: null, subagentType: 'general-purpose', description: 'task a4', agentType: 'general-purpose', running: false },
      { agentId: 'a5', parentAgentId: null, subagentType: 'general-purpose', description: 'task a5', running: true },
    ])
  })

  test('refreshed while an agent runs, often enough for its status to reach the plane within a second: its end is a stop, a new one a spawn', async () => {
    expect(AGENTS_REFRESH_MS).toBeLessThanOrEqual(500)
    const h = harness({ messages: [{}], agents: [listed('a1', 'running')] })
    await h.ready()
    h.setAgents([listed('a1', 'running'), listed('fork1', 'running', { type: 'fork' })])
    await h.fire(AGENTS_REFRESH_MS)
    expect(h.ofType('agent')).toEqual([expect.objectContaining({ phase: 'spawn', agentId: 'fork1', subagentType: 'fork', parentAgentId: null, description: 'task fork1' })])
    h.setAgents([listed('a1', 'completed'), listed('fork1', 'running', { type: 'fork' })])
    await h.fire(AGENTS_REFRESH_MS)
    expect(h.ofType('agent').slice(1)).toEqual([expect.objectContaining({ phase: 'stop', agentId: 'a1', agentType: 'general-purpose' })])
    // Only a finished agent leaves the list.
    h.setAgents([listed('a1', 'completed')])
    await h.fire(AGENTS_REFRESH_MS)
    expect(h.ofType('agent').slice(2)).toEqual([expect.objectContaining({ phase: 'stop', agentId: 'fork1' })])
    // None runs now: the list is no longer read until one does.
    const reads = h.agentLists()
    await h.fire(AGENTS_REFRESH_MS)
    expect(h.agentLists()).toBe(reads)
    expect(h.timers.some((t) => t.kind === 'after' && t.ms === AGENTS_REFRESH_MS && !t.cancelled)).toBe(false)
  })

  test('an agent the spawn hook reported is not spawned twice, though the list names it while the hook still runs', async () => {
    const h = harness()
    await h.ready()
    const spawn = { tool_use_id: 'tu1', prompt: 'p', description: 'scout', subagentType: 'Explore', background: false }
    await h.hook('agent.spawn', spawn)(h.engine, spawn, async () => {
      // The engine started it: the list names it before the hook has said so.
      h.setAgents([listed('a9', 'running', { type: 'Explore', description: 'scout' })])
      h.timers.find((t) => t.kind === 'every')!.fn()
      await h.settle()
      return { model: 'claude-haiku', agentId: 'a9' }
    })
    await h.settle()
    await h.fire(AGENTS_REFRESH_MS)
    expect(h.ofType('agent')).toEqual([expect.objectContaining({ phase: 'spawn', agentId: 'a9', background: false, model: 'claude-haiku', toolUseId: 'tu1' })])
  })

  test("the list's stop and the engine's SubagentStop say it once; an agent no list names (a workflow's) is not stopped by the refresh", async () => {
    const h = harness()
    await h.ready()
    for (const [agentId, tu] of [
      ['a9', 'tu1'],
      ['wf1', 'tu2'],
    ] as const) {
      const spawn = { tool_use_id: tu, prompt: 'p', description: 'd', subagentType: 'Explore', background: true }
      await h.hook('agent.spawn', spawn)(h.engine, spawn, async () => ({ model: 'm', agentId }))
    }
    h.setAgents([listed('a9', 'running')])
    await h.fire(AGENTS_REFRESH_MS)
    h.setAgents([listed('a9', 'failed')])
    await h.fire(AGENTS_REFRESH_MS)
    await h.hook('classic.SubagentStop', { hook_event_name: 'SubagentStop' })(h.engine, { hook_event_name: 'SubagentStop', agent_id: 'a9', agent_type: 'Explore' }, async () => ({}))
    await h.settle()
    expect(h.ofType('agent').map((e) => [e.phase, e.agentId])).toEqual([
      ['spawn', 'a9'],
      ['spawn', 'wf1'],
      ['stop', 'a9'],
    ])
  })

  test('an agent that starts while none runs is learned at the heartbeat, or at once when its loop starts a turn', async () => {
    const h = harness()
    await h.ready()
    h.setAgents([listed('k1', 'running', { type: 'fork' })])
    h.timers.find((t) => t.kind === 'every')!.fn()
    await h.settle()
    expect(h.ofType('agent').map((e) => [e.phase, e.agentId])).toEqual([['spawn', 'k1']])
    h.setAgents([listed('k1', 'running', { type: 'fork' }), listed('k2', 'running', { type: 'fork' })])
    await h.turn('t-k2', 'k2')
    await h.settle()
    expect(h.ofType('agent').map((e) => [e.phase, e.agentId])).toEqual([
      ['spawn', 'k1'],
      ['spawn', 'k2'],
    ])
  })

  test("after a /clear, the agents of the conversation before it are not seeded into the new session's state", async () => {
    const h = harness({ messages: [{}], agents: [listed('old1', 'completed'), listed('old2', 'running')] })
    await h.ready()
    await h.hook('session.end', {})(h.engine, { reason: 'clear', sessionId: SID }, async () => ({}))
    await h.settle()
    const NEW = '6c000002-0000-4000-8000-00000000006c'
    const NEWSOCK = `/tmp/s/bridge/${NEW}.sock`
    h.setSession(NEW)
    h.timers.filter((t) => t.kind === 'after' && t.ms !== AGENTS_REFRESH_MS && !t.cancelled).at(-1)!.fn()
    await h.settle()
    h.children[1]!.write(hello(NEW, NEWSOCK))
    await h.settle()
    h.timers.find((t) => t.kind === 'every' && !t.cancelled)!.fn()
    await h.settle()
    const toNew = h.posts.filter((p) => p.socketPath === NEWSOCK).flatMap((p) => p.events)
    expect(toNew.find((e) => e.type === 'resync')!.agents).toEqual([])
    expect(toNew.filter((e) => e.type === 'agent')).toEqual([])
  })

  test('a list that cannot be read changes nothing', async () => {
    const h = harness({ messages: [{}] })
    ;(h.engine as unknown as { agent: { list: () => Promise<unknown> } }).agent.list = async () => {
      throw new Error('no list')
    }
    await h.ready()
    expect(h.events()[1]!.agents).toEqual([])
  })

  /** From here, each read of the list waits until the test answers it (or fails it, `null`), in any order. */
  const holdLists = (h: ReturnType<typeof harness>) => {
    const reads: ((agents: Record<string, unknown>[] | null) => void)[] = []
    ;(h.engine as unknown as { agent: { list: () => Promise<unknown> } }).agent.list = () =>
      new Promise((resolve, reject) => reads.push((agents) => (agents === null ? reject(new Error('no list')) : resolve(agents))))
    return reads
  }

  /**
   * A /clear, with `before` answering the reads begun before it (the /clear's
   * own among them); then the new session's child, and a read in the new
   * conversation that lists `then`. What reached the new child.
   */
  const clearWith = async (
    h: ReturnType<typeof harness>,
    reads: ReturnType<typeof holdLists>,
    before: () => Promise<void>,
    then: Record<string, unknown>[],
    after: () => Promise<void> = async () => undefined,
  ) => {
    await h.hook('session.end', {})(h.engine, { reason: 'clear', sessionId: SID }, async () => ({}))
    await h.settle()
    await before()
    const NEW = '6c000002-0000-4000-8000-00000000006c'
    const NEWSOCK = `/tmp/s/bridge/${NEW}.sock`
    h.setSession(NEW)
    h.timers.filter((t) => t.kind === 'after' && t.ms !== AGENTS_REFRESH_MS && !t.cancelled).at(-1)!.fn()
    await h.settle()
    h.children[1]!.write(hello(NEW, NEWSOCK))
    await h.settle()
    h.timers.find((t) => t.kind === 'every' && !t.cancelled)!.fn()
    await h.settle()
    reads.at(-1)!(then)
    await h.settle()
    await after()
    return h.posts.filter((p) => p.socketPath === NEWSOCK).flatMap((p) => p.events)
  }

  test('reads that overlap: an older list answered after a newer one changes nothing, so a running agent is not stopped', async () => {
    const h = harness({ messages: [{}], agents: [listed('a1', 'running')] })
    await h.ready()
    const reads = holdLists(h)
    h.timers.find((t) => t.kind === 'every')!.fn() // the heartbeat's read, begun first
    await h.settle()
    await h.fire(AGENTS_REFRESH_MS) // the timer's, begun after it
    expect(reads.length).toBe(2)
    reads[1]!([listed('a1', 'running')])
    await h.settle()
    reads[0]!([]) // older, and answered last: a1 gone from it
    await h.settle()
    expect(h.ofType('agent')).toEqual([])
    const later = reads.length
    await h.fire(AGENTS_REFRESH_MS)
    reads[later]!([listed('a1', 'completed')])
    await h.settle()
    expect(h.ofType('agent').map((e) => [e.phase, e.agentId])).toEqual([['stop', 'a1']])
  })

  test("a read begun before a /clear and answered after it does not bring the old conversation's agents into the new one", async () => {
    const h = harness({ messages: [{}] })
    await h.ready()
    const reads = holdLists(h)
    h.timers.find((t) => t.kind === 'every')!.fn() // a read in flight, before the /clear
    await h.settle()
    const toNew = await clearWith(
      h,
      reads,
      async () => {
        expect(reads.length).toBe(2) // and the one the /clear makes, which fails here, and fails again
        reads[0]!([listed('old9', 'running')]) // an agent of the old conversation nobody knew yet
        reads[1]!(null)
        await h.settle()
        reads[2]!(null)
        await h.settle()
      },
      // The engine's list goes on naming it: a read in the new conversation still does not take it.
      [listed('old9', 'running'), listed('new1', 'running', { type: 'fork' })],
    )
    expect(toNew.find((e) => e.type === 'resync')!.agents).toEqual([])
    expect(toNew.filter((e) => e.type === 'agent').map((e) => [e.phase, e.agentId])).toEqual([['spawn', 'new1']])
  })

  test("at a /clear the list is read once more: an old agent nobody knew is not the new conversation's either", async () => {
    const h = harness({ messages: [{}] })
    await h.ready()
    const reads = holdLists(h)
    const toNew = await clearWith(
      h,
      reads,
      async () => {
        expect(reads.length).toBe(1)
        reads[0]!([listed('old8', 'running')])
        await h.settle()
      },
      [listed('old8', 'running'), listed('new2', 'running', { type: 'fork' })],
    )
    expect(toNew.filter((e) => e.type === 'agent').map((e) => [e.phase, e.agentId])).toEqual([['spawn', 'new2']])
  })

  test('a read outstanding at a /clear and answered last, after a new read: the new read waits for it, so it seeds nothing it names', async () => {
    const h = harness({ messages: [{}] })
    await h.ready()
    const reads = holdLists(h)
    h.timers.find((t) => t.kind === 'every')!.fn() // outstanding at the /clear
    await h.settle()
    const toNew = await clearWith(
      h,
      reads,
      async () => {
        // The /clear's own read fails, and so does its retry.
        reads[1]!(null)
        await h.settle()
        reads[2]!(null)
        await h.settle()
      },
      [listed('old9', 'running'), listed('new1', 'running', { type: 'fork' })],
      async () => {
        expect(h.posts.flatMap((p) => p.events).filter((e) => e.type === 'agent')).toEqual([]) // still waiting
        reads[0]!([listed('old9', 'running')]) // the old conversation's answer, last of all
        await h.settle()
      },
    )
    expect(toNew.find((e) => e.type === 'resync')!.agents).toEqual([])
    expect(toNew.filter((e) => e.type === 'agent').map((e) => [e.phase, e.agentId])).toEqual([['spawn', 'new1']])
  })

  test("a /clear's own read that fails once is tried again", async () => {
    const h = harness({ messages: [{}] })
    await h.ready()
    const reads = holdLists(h)
    const toNew = await clearWith(
      h,
      reads,
      async () => {
        reads[0]!(null)
        await h.settle()
        expect(reads.length).toBe(2)
        reads[1]!([listed('old7', 'running')])
        await h.settle()
      },
      [listed('old7', 'running'), listed('new3', 'running', { type: 'fork' })],
    )
    expect(toNew.filter((e) => e.type === 'agent').map((e) => [e.phase, e.agentId])).toEqual([['spawn', 'new3']])
  })

  /**
   * A /clear whose own read fails, and whose retry is answered (`[old7,
   * fork1]`) only after the new conversation has started its fork `fork1`:
   * `race` orders the fork's first turn and that answer. What reached the new
   * child.
   */
  const retryRace = async (race: (h: ReturnType<typeof harness>, reads: ReturnType<typeof holdLists>, retry: () => Promise<void>) => Promise<void>) => {
    const h = harness({ messages: [{}] })
    await h.ready()
    const reads = holdLists(h)
    const both = [listed('old7', 'running'), listed('fork1', 'running', { type: 'fork' })]
    const retry = async () => {
      reads[1]!(both)
      await h.settle()
    }
    const toNew = await clearWith(
      h,
      reads,
      async () => {
        reads[0]!(null) // the /clear's own read fails; its retry (reads[1]) is not answered yet
        await h.settle()
        expect(reads.length).toBe(2)
      },
      both, // the new conversation's heartbeat read, waiting on the retry
      async () => {
        await race(h, reads, retry)
        // Every read since is answered with the list as it stands.
        for (let i = 3; i < reads.length; i++) {
          reads[i]!(both)
          await h.settle()
        }
      },
    )
    return toNew.filter((e) => e.type === 'agent').map((e) => [e.phase, e.agentId])
  }

  test("a /clear's retry answered after the new conversation's fork started its turn does not hide the fork", async () => {
    const agents = await retryRace(async (h, _reads, retry) => {
      await h.turn('t-f', 'fork1')
      await h.settle()
      await retry()
    })
    expect(agents).toEqual([['spawn', 'fork1']])
  })

  test("a /clear's retry that names the new conversation's fork before its turn starts sets it aside only until that turn", async () => {
    const agents = await retryRace(async (h, _reads, retry) => {
      await retry()
      await h.turn('t-f', 'fork1')
      await h.settle()
    })
    expect(agents).toEqual([['spawn', 'fork1']])
  })

  test("a /clear's retry answered while the new conversation's spawn hook runs: the agent it spawns is that hook's, and the list may end it", async () => {
    const h = harness({ messages: [{}] })
    await h.ready()
    const reads = holdLists(h)
    const toNew = await clearWith(
      h,
      reads,
      async () => {
        reads[0]!(null)
        await h.settle()
      },
      [],
      async () => {
        const spawn = { tool_use_id: 'tu9', prompt: 'p', description: 'scout', subagentType: 'Explore', background: true }
        await h.hook('agent.spawn', spawn)(h.engine, spawn, async () => {
          reads[1]!([listed('old7', 'running'), listed('s9', 'running', { type: 'Explore' })])
          await h.settle()
          return { model: 'claude-haiku', agentId: 's9' }
        })
        await h.settle()
        await h.fire(AGENTS_REFRESH_MS)
        reads.at(-1)!([listed('old7', 'running'), listed('s9', 'completed', { type: 'Explore' })])
        await h.settle()
      },
    )
    expect(toNew.filter((e) => e.type === 'agent').map((e) => [e.phase, e.agentId])).toEqual([
      ['spawn', 's9'],
      ['stop', 's9'],
    ])
  })
})

describe('streaming per content block', () => {
  test("each response row names its block by the row's type and the order of the step's block starts, not its own position; the resync carries a named block with its row's uuid until the step ends", async () => {
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
      const named = h.ofType('block-row')[0]!
      // A new child mid-step gets every block of the open request, the named one
      // still carrying its text, marked with the row that named it and when.
      h.children[0]!.write(hello())
      await h.settle()
      const resync = h.ofType('resync').at(-1)!
      // It declares that it keeps named blocks, so the child's snapshot may say so.
      expect(resync).toMatchObject({ type: 'resync', namedBlocks: true })
      expect(resync.streaming).toEqual([
        {
          turnId: 't1',
          agentId: null,
          step: 0,
          model: 'm',
          upTo: 3,
          blocks: [
            { index: 0, kind: 'thinking', text: 'hm', upTo: 0, uuid: 'r-think', namedAt: named.t },
            { index: 1, kind: 'text', text: 'Hi', upTo: 1 },
            { index: 2, kind: 'tool', text: '{"c', upTo: 3, id: 'toolu_9', name: 'Bash' },
          ],
          // The blocks a row settled, so a child that takes this over ignores their late chunks.
          settled: [0],
        },
      ])
      // The tool's row before the text's: the tool by its call id, the text by kind.
      await h.responseRow({ type: 'tool_use', id: 'toolu_9', name: 'Bash', input: {} }, { uuid: 'r-tool' })
      await h.responseRow({ type: 'text', text: 'Hi' }, { uuid: 'r-text' })
    })
    expect(h.ofType('block-row')).toEqual([
      expect.objectContaining({ uuid: 'r-think', turnId: 't1', agentId: null, step: 0, index: 0 }),
      expect.objectContaining({ uuid: 'r-tool', turnId: 't1', agentId: null, step: 0, index: 2 }),
      expect.objectContaining({ uuid: 'r-text', turnId: 't1', agentId: null, step: 0, index: 1 }),
    ])
    // Its step over, the request and its named blocks are in no later resync.
    h.children[0]!.write(hello())
    await h.settle()
    expect(h.ofType('resync').at(-1)!.streaming).toEqual([])
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

describe("a post fits the engine's limit", () => {
  /** Letters a..z in turn, `size` of each: a tail of them shows where it was cut. */
  const pieces = (n: number, size: number) => Array.from({ length: n }, (_, i) => String.fromCharCode(97 + (i % 26)).repeat(size))
  type Shown = { agentId: string | null; blocks: Record<string, unknown>[] }

  test('a tool input streaming 5,000,000 characters, then a new child: every post fits; the resync, alone in its post, carries the last BLOCK_TAIL characters marked truncated; no gap, no second resync', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const json = pieces(5_000, 1_000)
    const whole = json.join('')
    const chunks = [{ kind: 'tool', index: 0, id: 'toolu_big', name: 'Write' }, ...json.map((j) => ({ kind: 'input', index: 0, json: j }))]
    let resynced = 0
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, chunks, async () => {
      await h.settle()
      // The child is killed mid-stream; its successor says hello.
      const timers = h.timers.length
      h.children[0]!.end()
      await h.settle()
      h.timers[timers]!.fn()
      await h.settle()
      const before = h.posts.length
      h.children[1]!.write(hello())
      await h.settle()
      const resyncs = h.posts.slice(before).filter((p) => p.events.some((e) => e.type === 'resync'))
      resynced = resyncs.length
      expect(resyncs.map((p) => p.events.length)).toEqual([1])
      const streaming = resyncs[0]!.events[0]!.streaming as Shown[]
      expect(streaming.map((m) => m.blocks.length)).toEqual([1])
      const block = streaming[0]!.blocks[0]!
      const { text: _text, ...rest } = block
      expect(rest).toEqual({ index: 0, kind: 'tool', id: 'toolu_big', name: 'Write', upTo: 5_000, truncated: true })
      // Compared, not diffed: a failure's report would carry the strings whole.
      expect((block.text as string).length).toBe(BLOCK_TAIL)
      expect(block.text === whole.slice(-BLOCK_TAIL)).toBe(true)
    })
    expect(resynced).toBe(1)
    expect(h.posts.filter((p) => p.size > ENGINE_BODY_MAX).map((p) => p.size)).toEqual([])
    expect(h.ofType('gap')).toEqual([])
    // The ready's resync and the successor's, no other.
    expect(h.ofType('resync').length).toBe(2)
    // Chunk events stay whole: a subscriber that streamed from the start holds every character.
    const streamed = h
      .ofType('chunk')
      .map((e) => (e.chunk as { json?: string }).json ?? '')
      .join('')
    expect(streamed === whole).toBe(true)
  })

  test('a resync past RESYNC_MAX drops streaming messages oldest first, and says so', async () => {
    const h = harness()
    await h.ready()
    // Three loops streaming at once, each 25 blocks cut to their tail: about 1.6 M characters a message.
    const blocks = (letter: string) => Array.from({ length: 25 }, (_, i) => ({ kind: 'text', index: i, text: letter.repeat(70_000) }))
    let resync: Record<string, unknown> | undefined
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, blocks('a'), async () => {
      await h.step({ turnId: 'ts', index: 0, model: 'm', messageCount: 1, agentId: 'a7' }, blocks('b'), async () => {
        await h.step({ turnId: 'tu', index: 0, model: 'm', messageCount: 1, agentId: 'a8' }, blocks('c'), async () => {
          await h.settle()
          h.children[0]!.write(hello())
          await h.settle()
          resync = h.ofType('resync').at(-1)
        })
      })
    })
    expect(resync?.truncated).toBe(true)
    const streaming = resync!.streaming as Shown[]
    expect(streaming.map((m) => m.agentId)).toEqual(['a7', 'a8'])
    expect(streaming.flatMap((m) => m.blocks).map((b) => [b.truncated, (b.text as string).length])).toEqual(Array(50).fill([true, BLOCK_TAIL]))
    expect(JSON.stringify(resync).length).toBeLessThanOrEqual(RESYNC_MAX)
    expect(h.posts.filter((p) => p.size > ENGINE_BODY_MAX).map((p) => p.size)).toEqual([])
    expect(h.ofType('gap')).toEqual([])
  })

  test('a block of exactly BLOCK_TAIL UTF-16 units is whole; one unit more is cut to its last BLOCK_TAIL', async () => {
    const h = harness()
    await h.ready()
    let resync: Record<string, unknown> | undefined
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'x'.repeat(BLOCK_TAIL) }, { kind: 'text', index: 1, text: `y${'x'.repeat(BLOCK_TAIL)}` }], async () => {
      h.children[0]!.write(hello())
      await h.settle()
      resync = h.ofType('resync').at(-1)
    })
    const [exact, over] = (resync!.streaming as Shown[])[0]!.blocks
    expect([exact!.truncated, (exact!.text as string).length]).toEqual([undefined, BLOCK_TAIL])
    expect([over!.truncated, (over!.text as string).length, (over!.text as string).startsWith('y')]).toEqual([true, BLOCK_TAIL, false])
  })

  test("a cut that would split a surrogate pair drops the pair's lone half: the tail is BLOCK_TAIL - 1 units and starts on a whole character", async () => {
    const h = harness()
    await h.ready()
    // One unit of 'x', then astral characters: the last BLOCK_TAIL units begin on a low surrogate.
    const text = `x${'😀'.repeat(BLOCK_TAIL / 2)}z`
    let resync: Record<string, unknown> | undefined
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text }], async () => {
      h.children[0]!.write(hello())
      await h.settle()
      resync = h.ofType('resync').at(-1)
    })
    const block = (resync!.streaming as Shown[])[0]!.blocks[0]!
    const tail = block.text as string
    expect(tail.length).toBe(BLOCK_TAIL - 1)
    expect(tail.charCodeAt(0)).toBe(0xd83d)
    expect(tail === text.slice(-(BLOCK_TAIL - 1))).toBe(true)
  })

  test('the bound counts UTF-16 units, as the engine measures a body: astral text is cut at half as many characters (the child counts code points, bridge_order pins it)', async () => {
    const h = harness()
    await h.ready()
    const text = '😀'.repeat(40_000)
    let resync: Record<string, unknown> | undefined
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text }], async () => {
      h.children[0]!.write(hello())
      await h.settle()
      resync = h.ofType('resync').at(-1)
    })
    const block = (resync!.streaming as Shown[])[0]!.blocks[0]!
    expect([block.truncated, (block.text as string).length, [...(block.text as string)].length]).toEqual([true, BLOCK_TAIL, BLOCK_TAIL / 2])
  })

  test('a resync under RESYNC_MAX is whole and says nothing of truncation', async () => {
    const h = harness()
    await h.ready()
    await h.step({ turnId: 't1', index: 0, model: 'm', messageCount: 1 }, [{ kind: 'text', index: 0, text: 'short' }], async () => {
      h.children[0]!.write(hello())
      await h.settle()
    })
    const resync = h.ofType('resync').at(-1)!
    expect('truncated' in resync).toBe(false)
    expect((resync.streaming as Shown[])[0]!.blocks).toEqual([{ index: 0, kind: 'text', text: 'short', upTo: 0 }])
  })

  test("a resync whose pending requests alone pass RESYNC_MAX shortens the permissions' inputs, largest first, each marked truncated: every request keeps its id and tool, and the post fits", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    // 65 Write permissions pending, each input at the per-string cap.
    const content = 'w'.repeat(TEXT_CAP)
    for (let i = 0; i < 65; i++) {
      const input = { file_path: `/w/f${i}`, content }
      await h.called(`toolu_w${i}`, 'Write', input)
      void h.permission('Write', input)
      await h.settle()
    }
    expect(h.ofType('raised').length).toBe(65)
    h.children[0]!.write(hello())
    await h.settle()
    const resync = h.ofType('resync').at(-1)!
    expect(resync.truncated).toBe(true)
    expect(JSON.stringify(resync).length).toBeLessThanOrEqual(RESYNC_MAX)
    const pending = resync.pending as { request: string; tool: string; input: { file_path: string; content: string }; truncated?: boolean }[]
    expect(pending.map((p) => [p.request, p.tool, p.input.file_path])).toEqual(Array.from({ length: 65 }, (_, i) => [`toolu_w${i}`, 'Write', `/w/f${i}`]))
    const shortened = pending.filter((p) => p.input.content.length < TEXT_CAP)
    expect(shortened.length).toBeGreaterThan(0)
    expect(shortened.length).toBeLessThan(65)
    expect(shortened.every((p) => p.truncated === true && p.input.content.length === RESYNC_INPUT_CAP)).toBe(true)
    expect(h.posts.filter((p) => p.size > ENGINE_BODY_MAX).map((p) => p.size)).toEqual([])
    expect(h.ofType('gap')).toEqual([])
  })

  test('a shortened input never ends inside a surrogate pair, in a resync as in a raise past TEXT_CAP: each string stays well-formed, so it has a canonical form to seal', async () => {
    // A lone surrogate: a high one with no low after it, or a low one with no high before it.
    const lone = /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/
    const h = harness()
    await h.ready()
    await h.turn('t1')
    // 65 Write permissions, each a well-formed 65,535-unit string: inside TEXT_CAP, so raised whole.
    const content = 'x' + '😀'.repeat((TEXT_CAP - 2) / 2)
    for (let i = 0; i < 65; i++) {
      const input = { file_path: `/w/f${i}`, content }
      await h.called(`toolu_w${i}`, 'Write', input)
      void h.permission('Write', input)
      await h.settle()
    }
    // And one past TEXT_CAP, cut as it is raised: its 65,536th unit is a high surrogate.
    const long = { file_path: '/w/long', content: 'x' + '😀'.repeat(TEXT_CAP / 2) }
    await h.called('toolu_long', 'Write', long)
    void h.permission('Write', long)
    await h.settle()
    const raisedLong = h.ofType('raised').find((e) => e.request === 'toolu_long')!
    const cut = (raisedLong.input as { content: string }).content
    expect([raisedLong.truncated, cut.length, lone.test(cut)]).toEqual([true, TEXT_CAP - 1, false])
    h.children[0]!.write(hello())
    await h.settle()
    const resync = h.ofType('resync').at(-1)!
    expect(resync.truncated).toBe(true)
    const pending = resync.pending as { request: string; input: { content: string }; truncated?: boolean }[]
    const shortened = pending.filter((p) => p.input.content.length < TEXT_CAP - 1)
    expect(shortened.length).toBeGreaterThan(0)
    expect(shortened.map((p) => [p.truncated, p.input.content.length, lone.test(p.input.content)])).toEqual(
      shortened.map(() => [true, RESYNC_INPUT_CAP - 1, false]),
    )
  })

  test("a question's input is kept whole when a resync is shortened: its answers are matched against it", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const content = 'w'.repeat(TEXT_CAP)
    for (let i = 0; i < 64; i++) {
      const input = { file_path: `/w/f${i}`, content }
      await h.called(`toolu_w${i}`, 'Write', input)
      void h.permission('Write', input)
      await h.settle()
    }
    const question = 'q'.repeat(TEXT_CAP)
    const ask = { questions: [{ question, header: 'H', options: [{ label: 'a' }, { label: 'b' }], multiSelect: false }] }
    await h.called('toolu_q', 'AskUserQuestion', ask)
    void h.permission('AskUserQuestion', ask)
    await h.settle()
    h.children[0]!.write(hello())
    await h.settle()
    const resync = h.ofType('resync').at(-1)!
    expect(JSON.stringify(resync).length).toBeLessThanOrEqual(RESYNC_MAX)
    const asked = (resync.pending as { request: string; input: typeof ask; truncated?: boolean }[]).find((p) => p.request === 'toolu_q')!
    expect(asked.input.questions[0]!.question === question).toBe(true)
    expect(asked.truncated).toBeUndefined()
  })

  test('what queued while a post was in flight goes in posts that each fit, in order, nothing lost', async () => {
    const h = harness({ hold: true })
    const releaseAll = async () => {
      for (let i = 0; i < h.posts.length; i++) {
        h.posts[i]!.release()
        await h.settle()
      }
    }
    await h.ready()
    await releaseAll()
    const held = h.posts.length
    // A post in flight; behind it, 6 M characters of chunks.
    await h.hook('turn.start', { turnId: 't1' })(h.engine, { turnId: 't1', text: '' }, async () => ({ turnId: 't1' }))
    await h.settle()
    const text = pieces(100, 60_000)
    const e = { turnId: 't1', index: 0, model: 'm', messageCount: 1 }
    const gen = h.hook('turn.step', e)(h.engine, e, () => {
      const g = (async function* () {
        for (const t of text) {
          yield { kind: 'text', index: 0, text: t }
        }
        return { turnId: 't1', index: 0, answer: '', toolUses: [], stopReason: 'end_turn', usage: null }
      })() as AsyncGenerator<unknown, unknown> & { result: Promise<unknown> }
      g.result = Promise.resolve({ turnId: 't1', index: 0, stopReason: 'end_turn', usage: null })
      return g
    }) as AsyncGenerator<unknown, unknown>
    for (let r = await gen.next(); !r.done; r = await gen.next()) {
      // the stream passes on
    }
    await h.settle()
    await releaseAll()
    expect(h.posts.filter((p) => p.size > ENGINE_BODY_MAX).map((p) => p.size)).toEqual([])
    expect(h.posts.length).toBeGreaterThan(held + 2)
    expect(h.ofType('gap')).toEqual([])
    expect(h.ofType('chunk').map((c) => c.chunkIndex)).toEqual(text.map((_, i) => i))
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
    await h.called('toolu_1', 'Bash', INPUT)
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
    await h.called('toolu_1', 'Bash', INPUT)
    expect(await h.permission('Bash', INPUT, undefined, { decision: { behavior: 'deny', message: 'policy' } })).toEqual({ decision: { behavior: 'deny', message: 'policy' } })
    expect(h.ofType('raised')).toEqual([])
    expect(h.polls).toEqual([])
  })

  test('two identical calls, the first decided beneath: the second is raised under its own id, and answered from outside', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.called('toolu_1', 'Bash', INPUT)
    await h.permission('Bash', INPUT, undefined, { decision: { behavior: 'allow' } })
    await h.called('toolu_2', 'Bash', INPUT)
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
    await h.called('toolu_1', 'Bash', INPUT)
    await h.recorded('toolu_1', 'config')
    await h.called('toolu_2', 'Bash', INPUT)
    void h.permission('Bash', INPUT)
    ;(await h.nextPoll()).respond(410, { reason: 'settled' })
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'toolu_2' })])
  })

  test('answered at the dialog while the settings hooks beneath still ran: nothing is raised', async () => {
    const h = harness()
    await h.ready()
    await h.called('toolu_1', 'Bash', INPUT)
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
    await h.called('toolu_1', 'Bash', INPUT)
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

  test("a permission for a call the bridge did not see is the terminal's: nothing is raised, and the debug log says why", async () => {
    const h = harness()
    await h.ready()
    // No check named it, or one did whose call this module never saw (it began before a reload).
    expect(await h.permission('Bash', INPUT)).toEqual({})
    await h.check('toolu_9', 'Bash', INPUT)
    expect(await h.permission('Bash', INPUT)).toEqual({})
    expect(h.ofType('raised')).toEqual([])
    expect(h.polls).toEqual([])
    expect(h.logs.filter((l) => l.includes('did not see')).length).toBe(2)
  })

  test('a question no check named still raises a request, under an id of its own', async () => {
    const h = harness()
    await h.ready()
    void h.permission('AskUserQuestion', { questions: [{ question: 'Which?', header: 'Q', multiSelect: false, options: [] }] })
    const poll = await h.nextPoll()
    const id = String(h.ofType('raised')[0]?.request)
    expect(id).toMatch(/^request-/)
    expect(poll.url).toBe(`http://bridge/requests/${id}/wait?ms=20000`)
    poll.respond(410, { reason: 'settled' })
  })

  test('a resync carries the pending requests and the recent settlements', async () => {
    const { h, answer, poll } = await raised()
    await h.called('toolu_2', 'Bash', { command: 'ls' })
    void h.permission('Bash', { command: 'ls' })
    const second = await h.nextPoll()
    poll.respond(410, { reason: 'terminal' })
    await answer
    await h.recorded('toolu_1', 'user_reject', 'reject')
    h.children[0]!.write(hello())
    await h.settle()
    const resync = h.ofType('resync').at(-1)!
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
    await h.called('toolu_b', 'Bash', INPUT, 'a9')
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
    await h.called('toolu_b', 'Bash', INPUT, 'a9')
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
    await h.called('toolu_u', 'Bash', INPUT, 'a-unknown')
    void h.permission('Bash', INPUT, 'a-unknown')
    ;(await h.nextPoll()).respond(410, { reason: 'settled' })
    expect(h.ofType('raised')[0]).toHaveProperty('deadline')
    await h.turn('t1')
    await spawn(h, 'a5', false)
    await h.called('toolu_f', 'Bash', INPUT, 'a5')
    void h.permission('Bash', INPUT, 'a5')
    ;(await h.nextPoll()).respond(410, { reason: 'settled' })
    expect(h.ofType('raised')[1]).toMatchObject({ request: 'toolu_f', agentId: 'a5' })
    expect(h.ofType('raised')[1]).not.toHaveProperty('deadline')
  })
})

describe('requests from outside: a secrets guard that restores handles in tool.call', () => {
  // Fake: never a real secret.
  const HANDLE = '[secret:API_KEY]'
  const VALUE = 'sk-fake-0123456789abcdef'
  const MODEL = { command: `curl -H "Authorization: Bearer ${HANDLE}" https://api.example`, description: 'probe' }
  const RESTORED = { ...MODEL, command: MODEL.command.replaceAll(HANDLE, VALUE) }
  type Next = (e: Record<string, unknown>) => Promise<Record<string, unknown>>
  /**
   * devcloud's tool.call hook (devcloud/hooks/mods/secrets.tsx): the handle's
   * bytes into the call before `next`, every string of the result record
   * scrubbed after it. It answers `{ result, context }` when it scrubbed
   * something (no `text`: core sets that, never a hook's own result), and
   * `ran` itself otherwise.
   */
  const guard = async (e: Record<string, unknown>, next: Next) => {
    const ran = await next({ ...e, command: String(e.command).replaceAll(HANDLE, VALUE) })
    const record = ran.result as Record<string, unknown>
    const result = Object.fromEntries(Object.entries(record).map(([k, v]) => [k, typeof v === 'string' ? v.replaceAll(VALUE, HANDLE) : v]))
    return Object.entries(result).some(([k, v]) => v !== record[k]) ? { result, context: ran.context } : ran
  }
  /**
   * The engine beneath every tool.call hook: its check and its dialog's
   * PermissionRequest get the call as the hooks above handed it down (the
   * check's input is pinned: no hook can hand it the handles); an allow runs
   * the call, whose output echoes the command.
   */
  const engine = (h: ReturnType<typeof harness>, seen: unknown[], answers: unknown[]) => async (e: Record<string, unknown>) => {
    const input = { command: e.command, description: e.description }
    seen.push(input)
    await h.check('toolu_s', 'Bash', input)
    const answer = await h.permission('Bash', input)
    answers.push(answer)
    const text = (answer.decision as { behavior?: string } | undefined)?.behavior === 'allow' ? `ran: ${String(e.command)}` : 'refused'
    // Core's shape: the result record and the text it renders.
    return { result: { stdout: text, stderr: '', interrupted: false }, text }
  }
  const bridge = (h: ReturnType<typeof harness>) => (e: Record<string, unknown>, next: Next) => h.hook('tool.call', { tool: 'Bash' })(h.engine, e, next) as Promise<Record<string, unknown>>
  const CALL = { tool: 'Bash', tool_use_id: 'toolu_s', ...MODEL }
  const posted = (h: ReturnType<typeof harness>) => JSON.stringify(h.posts.map((p) => p.events))

  test("the guard beneath the bridge (sminos seated outside it): the raise, a resync's pending and the call's events carry the handle, while the engine decides and runs the restored call", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const seen: unknown[] = []
    const answers: unknown[] = []
    const ran = bridge(h)(CALL, (e) => guard(e, engine(h, seen, answers)))
    const poll = await h.nextPoll()
    expect(seen).toEqual([RESTORED])
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'toolu_s', tool: 'Bash', input: MODEL })])
    h.children[0]!.write(hello())
    await h.settle()
    expect(h.ofType('resync').at(-1)).toMatchObject({ pending: [expect.objectContaining({ request: 'toolu_s', input: MODEL })] })
    poll.respond(200, { decision: { behavior: 'allow' }, by: 'm-1' })
    // The allow hands no input back: the engine runs its own, restored.
    // The guard beneath scrubbed the result: the bridge's return is its `{ result, context }`, no text.
    expect(await ran).toEqual({ result: { stdout: `ran: ${MODEL.command}`, stderr: '', interrupted: false }, context: undefined })
    expect(answers).toEqual([{ decision: { behavior: 'allow' } }])
    // The call event carries the handle, and so does the result event's text, drawn from the scrubbed record.
    expect(h.ofType('tool').flatMap((e) => (e.input === undefined ? [] : [e.input]))).toEqual([MODEL])
    const result = h.ofType('tool').find((e) => e.phase === 'result')
    expect(typeof result?.text).toBe('string')
    expect(JSON.parse(String(result?.text))).toEqual({ stdout: `ran: ${MODEL.command}`, stderr: '', interrupted: false })
    expect(posted(h)).toContain(HANDLE)
    expect(posted(h)).not.toContain(VALUE)
  })

  test('a hook beneath answering content blocks (text and an image): the result event draws the text blocks, none of the image data', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const IMAGE = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk'
    const answer = [
      { type: 'text', text: 'the picture:' },
      { type: 'image', source: { type: 'base64', media_type: 'image/png', data: IMAGE } },
    ]
    await bridge(h)(CALL, async () => ({ result: answer, context: undefined }))
    await h.settle()
    const result = h.ofType('tool').find((e) => e.phase === 'result')
    expect(result?.text).toBe('the picture:')
    expect(posted(h)).not.toContain(IMAGE)
  })

  test('the guard outside the bridge (no prependPlugins): the bridge is handed the restored call, so its raise carries the value, as its call event and result do', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const seen: unknown[] = []
    const ran = guard(CALL, (e) => bridge(h)(e, engine(h, seen, [])))
    const poll = await h.nextPoll()
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'toolu_s', input: RESTORED })])
    poll.respond(200, { decision: { behavior: 'allow' }, by: 'm-1' })
    await ran
    expect(h.ofType('tool').map((e) => e.input ?? e.text)).toEqual([RESTORED, `ran: ${RESTORED.command}`])
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

  /** The ask mod's hooks, registered apart from the harness's, its state cleared. */
  const askHooks = () => {
    resetAsk()
    const hooks: { event: string; matcher?: Record<string, unknown>; handler: (...args: unknown[]) => Promise<unknown> }[] = []
    registerAsk(((event: string, ...rest: unknown[]) => {
      hooks.push({ event, matcher: rest.length > 1 ? (rest[0] as Record<string, unknown>) : undefined, handler: rest.at(-1) as (typeof hooks)[number]['handler'] })
      return { catch: () => {} }
    }) as unknown as On)
    return hooks
  }

  test("an async question open before the bridge started (a reloaded module's, taken up from the last) is pending in its first resync", async () => {
    const asked = askHooks().find((x) => x.event === 'tool.call' && x.matcher?.tool === ASK_TOOL)
    await asked?.handler({ ui: { invalidate: () => {}, notify: async () => ({ isSent: true, channel: 'terminal_bell' }) } }, { tool: ASK_TOOL, tool_use_id: 'toolu_r1', questions: [FRUIT], async: true }, async () => ({}))
    const h = harness()
    await h.ready()
    expect(h.ofType('resync')[0]).toMatchObject({ pending: [expect.objectContaining({ request: 'toolu_r1', tool: ASK_TOOL, input: { questions: [FRUIT] }, async: true })] })
    resetAsk()
  })

  test("a resumed session's open async asks, read back from its transcript before the bridge started, are pending in its first resync, once; an answered one is not", async () => {
    const rebuild = askHooks().find((x) => x.event === 'classic.SessionStart')
    const call = (uuid: string, parentUuid: string | null, id: string) => ({
      type: 'assistant',
      uuid,
      parentUuid,
      message: { id: `msg_${id}`, role: 'assistant', content: [{ type: 'tool_use', id, name: ASK_TOOL, input: { questions: [FRUIT], async: true } }] },
    })
    const result = (uuid: string, parentUuid: string, id: string) => ({ type: 'user', uuid, parentUuid, message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: ASYNC_RESULT }] } })
    const transcript = [
      call('a1', null, 'toolu_done'),
      result('u1', 'a1', 'toolu_done'),
      { type: 'user', uuid: 'u2', parentUuid: 'u1', message: { role: 'user', content: `The doperpowers plugin sent a message:\n${deliveryText('toolu_done', answered('Apple'))}` } },
      call('a2', 'u2', 'toolu_open'),
      result('u3', 'a2', 'toolu_open'),
    ]
      .map((row) => JSON.stringify(row))
      .join('\n')
    const h = harness({ messages: [{}] })
    // The engine runs the SessionStart hooks, where the ask mod reads the asks
    // back, while the plugin's session.start still waits on its tool
    // registrations (live, 2.1.303): its notes come before the bridge started.
    await rebuild?.handler(
      { fs: { stat: async () => ({ size: transcript.length }), read: async () => transcript }, ui: { invalidate: () => {} } },
      { hook_event_name: 'SessionStart', source: 'resume', session_id: SID, transcript_path: '/p/resumed.jsonl', cwd: '/w' },
      async () => ({}),
    )
    await h.ready()
    expect(h.ofType('resync')[0]?.pending).toEqual([expect.objectContaining({ request: 'toolu_open', tool: ASK_TOOL, input: { questions: [FRUIT] }, agentId: null, async: true })])
    // A note that comes after the start (a rebuild slower than it) raises nothing twice.
    onAskNote({ kind: 'open', id: 'toolu_open', questions: [FRUIT] })
    await h.settle()
    expect(h.ofType('raised')).toEqual([])
    resetAsk()
  })

  test("the ask mod's blocking question: raised under its dialog with the outer call's toolUseId; the dialog's own call and result are not posted", async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    const fromPlugin = <T extends object>(fn: T) => Object.assign(fn, { origin: { kind: 'tool', plugin: PLUGIN } })
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
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'toolu_plugin_1', toolUseId: 'toolu_01outer', tool: 'AskUserQuestion', input: { questions: [FRUIT] } })])
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
      Object.assign(() => new Promise((resolve) => (endDialog = resolve)), { origin: { kind: 'tool', plugin: PLUGIN } }),
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

  test("MAWS's ask goes the same way when it does not wait (blocking false), and not when it does", async () => {
    const h = harness()
    await h.ready()
    const PROCEED = { id: 'q1', question: 'Proceed?', modality: 'choice', options: [{ label: 'Yes' }, { label: 'No' }] }
    const mawsUse = (id: string, blocking?: boolean) => ({ type: 'tool_use', id, name: 'mcp__maws__ask', input: { questions: [PROCEED], ...(blocking !== undefined && { blocking }) } })
    const mawsResult = (id: string, text: string) => ({ type: 'tool_result', tool_use_id: id, content: [{ type: 'text', text }] })
    const asked = (id: string) => JSON.stringify({ status: 'asked', askId: id }, null, 2)
    const answered = (id: string) => JSON.stringify({ status: 'answered', askId: id, answers: [] }, null, 2)
    const keep = (id: string, uuid: string, text: string) =>
      h.append('tool-result', { type: 'user', role: 'user', content: [mawsResult(id, text)] }, { uuid, origin: { kind: 'tool', tool: 'mcp__maws__ask' } })
    await keep('toolu_m1', 'r-mres1', asked('toolu_m1'))
    await h.responseRow(mawsUse('toolu_m1', false), { uuid: 'r-muse1' })
    await h.responseRow(mawsUse('toolu_m2'), { uuid: 'r-muse2' })
    await keep('toolu_m2', 'r-mres2', answered('toolu_m2'))
    await h.responseRow(mawsUse('toolu_m3', true), { uuid: 'r-muse3' })
    await keep('toolu_m3', 'r-mres3', answered('toolu_m3'))
    expect(h.ofType('export').map((e) => e.records)).toEqual([
      [
        { type: 'assistant', uuid: 'r-muse1', message: { content: [mawsUse('toolu_m1', false)] } },
        { type: 'user', uuid: 'r-mres1', message: { content: [mawsResult('toolu_m1', asked('toolu_m1'))] } },
      ],
    ])
  })

  // The message tools, by value: the to-human plugin's, and MAWS's in a MAWS launch.
  const MESSAGE_TOOL = 'mcp__to-human__message'
  const MAWS_MESSAGE_TOOL = 'mcp__maws__message'
  const messageUse = (id: string, name: string, text: string) => ({ type: 'tool_use', id, name, input: { text } })
  const messageResult = (id: string, isError = false) => ({ type: 'tool_result', tool_use_id: id, content: isError ? 'refused' : 'sent', ...(isError && { is_error: true }) })
  /** A message tool's result row, as the engine keeps it. */
  const keepMessageResult = (h: ReturnType<typeof harness>, id: string, uuid: string, tool = MESSAGE_TOOL, isError = false) =>
    h.append('tool-result', { type: 'user', role: 'user', content: [messageResult(id, isError)] }, { uuid, origin: { kind: 'tool', tool } })

  test("a message tool's call goes with its result, both rows in one export, under either tool's name, whichever row the engine keeps first; the child judges a refused one", async () => {
    const h = harness()
    await h.ready()
    await h.responseRow(messageUse('toolu_t1', MESSAGE_TOOL, 'Approve the dialog.'), { uuid: 'r-t1' })
    expect(h.ofType('export')).toEqual([])
    await keepMessageResult(h, 'toolu_t1', 'r-t1res')
    await keepMessageResult(h, 'toolu_t2', 'r-t2res', MAWS_MESSAGE_TOOL)
    await h.responseRow(messageUse('toolu_t2', MAWS_MESSAGE_TOOL, 'Built.'), { uuid: 'r-t2' })
    await h.responseRow(messageUse('toolu_t3', MESSAGE_TOOL, 'from a subagent'), { uuid: 'r-t3' })
    await keepMessageResult(h, 'toolu_t3', 'r-t3res', MESSAGE_TOOL, true)
    const use = (id: string, name: string, text: string, uuid: string) => ({ type: 'assistant', uuid, message: { content: [messageUse(id, name, text)] } })
    const result = (id: string, uuid: string, isError = false) => ({ type: 'user', uuid, message: { content: [messageResult(id, isError)] } })
    expect(h.ofType('export').map((e) => e.records)).toEqual([
      [use('toolu_t1', MESSAGE_TOOL, 'Approve the dialog.', 'r-t1'), result('toolu_t1', 'r-t1res')],
      [use('toolu_t2', MAWS_MESSAGE_TOOL, 'Built.', 'r-t2'), result('toolu_t2', 'r-t2res')],
      [use('toolu_t3', MESSAGE_TOOL, 'from a subagent', 'r-t3'), result('toolu_t3', 'r-t3res', true)],
    ])
  })

  test("a message past the events' cap is left to the Stop hook's export, in either row order, and said so in the debug log", async () => {
    const h = harness()
    await h.ready()
    const long = 'x'.repeat(TEXT_CAP + 1)
    await h.responseRow(messageUse('toolu_l1', MESSAGE_TOOL, long), { uuid: 'r-l1' })
    await keepMessageResult(h, 'toolu_l1', 'r-l1res')
    await keepMessageResult(h, 'toolu_l2', 'r-l2res', MAWS_MESSAGE_TOOL)
    await h.responseRow(messageUse('toolu_l2', MAWS_MESSAGE_TOOL, long), { uuid: 'r-l2' })
    expect(h.ofType('export')).toEqual([])
    expect(['r-l1', 'r-l2'].map((u) => h.logs.some((l) => l.includes(u) && l.includes('Stop hook')))).toEqual([true, true])
  })

  test("a message call whose result never came, and a message tool's call in a subagent, are not exported", async () => {
    const h = harness()
    await h.ready()
    await h.responseRow(messageUse('toolu_open', MESSAGE_TOOL, 'still running'), { uuid: 'r-open' })
    await h.responseRow(messageUse('toolu_sub', MESSAGE_TOOL, 'from a subagent'), { uuid: 'r-sub', agentId: 'a7' })
    await h.append('tool-result', { type: 'user', role: 'user', content: [messageResult('toolu_sub', true)] }, { uuid: 'r-subres', agentId: 'a7', origin: { kind: 'tool', tool: MESSAGE_TOOL } })
    expect(h.ofType('export')).toEqual([])
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

  // An answer's rows as the engine hands them to session.append: a prompt
  // row's text as kept, an attachment's as rendered (live, 2.1.300–302).
  const PLUGIN_PROMPT = `The ${PLUGIN} plugin sent a message:\n`
  const PLUGIN_FRAMING = "\n\nThis is how Claude Code surfaces a prompt a plugin submits between turns — it starts this turn in the user's place. Address the message above."
  const answer = (id: string) => deliveryText(id, 'The user answered: "Which fruit?"="Mango".')
  const steer = (id: string) =>
    `[MAWS ask ${id}] The user answered the questions you asked:\n1. Proceed? — Yes\n\`\`\`json\n${JSON.stringify({ status: 'answered', askId: id, answers: [] }, null, 2)}\n\`\`\``
  const midTurn = (prompt: string) =>
    `<system-reminder>\nThe user sent a new message while you were working:\n${prompt}\n\nThis is how Claude Code surfaces messages the user sends mid-turn — within the running turn, often alongside the next tool result, rather than as a separate conversation turn. Address the message above as you continue this turn.\n</system-reminder>`
  const prompt = (h: ReturnType<typeof harness>, text: string, uuid: string, origin: Record<string, unknown>, agentId?: string) =>
    h.append('prompt', { type: 'user', role: 'user', content: [{ type: 'text', text }] }, { uuid, origin, agentId })
  const context = (h: ReturnType<typeof harness>, text: string, uuid: string, name = 'hook_additional_context') =>
    h.append('hook-context', { type: 'attachment', name, role: 'user', isMeta: true, content: [{ type: 'text', text }] }, { uuid, origin: { kind: 'plugin', event: 'tool.call' } })
  const queued = (h: ReturnType<typeof harness>, text: string, uuid: string, render = midTurn) =>
    h.append('delivery', { type: 'attachment', name: 'queued_command', role: 'user', isMeta: true, content: [{ type: 'text', text: render(text) }] }, { uuid, origin: { kind: 'composer' } })
  const contextOf = (...entries: string[]) => `<system-reminder>\ntool.call hook additional context: ${entries.join('\n')}\n</system-reminder>`
  const exported = (h: ReturnType<typeof harness>) => h.ofType('export').map((e) => e.records)

  test("each row that may answer an ask goes to the child as it is kept, in the transcript's shape: the plugin's answer as a prompt or as context, MAWS's steer as a prompt or taken mid-turn", async () => {
    const h = harness()
    await h.ready()
    const submitted = `${PLUGIN_PROMPT}${answer('toolu_a1')}${PLUGIN_FRAMING}`
    await prompt(h, submitted, 'r-plugin', { kind: 'plugin', name: PLUGIN })
    await context(h, contextOf("another hook's line", answer('toolu_a2'), answer('toolu_a3')), 'r-context')
    await prompt(h, steer('toolu_m1'), 'r-steer', { kind: 'composer' })
    await queued(h, steer('toolu_m2'), 'r-queued')
    expect(exported(h)).toEqual([
      [{ type: 'user', uuid: 'r-plugin', origin: { kind: 'plugin', name: PLUGIN }, message: { content: [{ type: 'text', text: submitted }] } }],
      [{ type: 'attachment', uuid: 'r-context', attachment: { type: 'hook_additional_context', content: [`another hook's line\n${answer('toolu_a2')}\n${answer('toolu_a3')}`] } }],
      [{ type: 'user', uuid: 'r-steer', origin: { kind: 'human' }, message: { content: [{ type: 'text', text: steer('toolu_m1') }] } }],
      [{ type: 'attachment', uuid: 'r-queued', attachment: { type: 'queued_command', commandMode: 'prompt', prompt: steer('toolu_m2'), origin: { kind: 'human' } } }],
    ])
  })

  test('a mid-turn message that quotes a steer goes whole, never cut down to the steer it quotes: the child reads it as the human wrote it', async () => {
    const h = harness()
    await h.ready()
    const quoting = `Is this what MAWS sent?\n${steer('toolu_m5')}\nIt looks wrong to me.`
    await queued(h, quoting, 'r-quote')
    expect(exported(h)).toEqual([[{ type: 'attachment', uuid: 'r-quote', attachment: { type: 'queued_command', commandMode: 'prompt', prompt: quoting, origin: { kind: 'human' } } }]])
  })

  test("an attachment the engine's exact framing does not give back, or whose rendering holds an escape, is the Stop hook's, said in the debug log", async () => {
    const h = harness()
    await h.ready()
    // The engine writes `&lt;` for a system-reminder tag in a hook's context
    // (its ROe), in another sender's prompt and in an id'd reminder; a literal
    // one the human typed reads the same.
    await context(h, contextOf(deliveryText('toolu_a4', 'The user answered: "How?"="wrap it in &lt;system-reminder> tags".')), 'r-escaped')
    await queued(h, steer('toolu_m6').replace('Yes', 'Yes &lt;/system-reminder&gt;'), 'r-qescaped')
    await queued(h, steer('toolu_m7'), 'r-idwrapped', (p) => `<system-reminder id="0123456789abcdef">\n${p}\n</system-reminder id="0123456789abcdef">`)
    await context(h, answer('toolu_a5'), 'r-bare')
    expect(exported(h)).toEqual([])
    expect(['r-escaped', 'r-qescaped', 'r-idwrapped', 'r-bare'].map((u) => h.logs.some((l) => l.includes(u) && l.includes('Stop hook')))).toEqual([true, true, true, true])
  })

  test("an unrelated prompt or attachment, a subagent's answer, and an answer past the events' cap are not exported", async () => {
    const h = harness()
    await h.ready()
    await prompt(h, 'go on with the parser', 'r-go', { kind: 'composer' })
    await context(h, '<system-reminder>\nUserPromptSubmit hook additional context: the branch is main\n</system-reminder>', 'r-ctx')
    await context(h, answer('toolu_a1'), 'r-other', 'hook_success')
    await queued(h, 'and also the lexer', 'r-midturn')
    await prompt(h, steer('toolu_m3'), 'r-sub', { kind: 'composer' }, 'a7')
    await prompt(h, steer('toolu_m4') + 'x'.repeat(TEXT_CAP), 'r-long', { kind: 'composer' })
    expect(h.ofType('export')).toEqual([])
    expect(h.logs.some((l) => l.includes('r-long'))).toBe(true)
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
    h.timers.find((t) => t.kind === 'after' && t.ms === 0 && !t.cancelled)!.fn()
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

  test("another plugin's compaction (doperpowers' compact tool, its $.session.compact) reaches the bridge through its session.compact hook, and is named ahead of the resume prompt that plugin submits after it", async () => {
    const h = harness()
    await h.ready()
    await prompt(h, 'p0')
    h.disk.main = ['p0']
    // The compact mod's call raises session.compact through every plugin's
    // hooks but its own: the bridge, sminos's, sees it as it sees /compact.
    const fromDoperpowers = Object.assign(async () => result('sum'), { origin: { kind: 'tool', plugin: 'doperpowers' } })
    expect(await h.hook('session.compact', { trigger: 'manual' })(h.engine, { trigger: 'manual', messages: [] }, fromDoperpowers)).toEqual(result('sum'))
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
    // The session's start is answered; the resync follows in a post of its own.
    h.posts.forEach((p) => p.release())
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

describe("the bridge's place among the secrets guards (next.trace)", () => {
  const CALL = { tool: 'Bash', tool_use_id: 'tu1', command: 'cat notes.txt' }
  const OUTPUT = 'the contents of notes.txt'
  type Harness = ReturnType<typeof harness>
  type Beneath = { short?: boolean; origin?: string }
  /** A Bash call through the bridge's hook, these plugins' links settled beneath it. */
  const callBeneath = (h: Harness, plugins: string[], options: Beneath = {}) =>
    h.hook('tool.call', { tool: 'Bash' })(h.engine, CALL, beneath(async () => ({ text: OUTPUT }), plugins, options)) as Promise<Record<string, unknown>>
  /** A call through the bridge's hook that runs until the test ends it. */
  const runningBeneath = async (h: Harness, plugins: string[]) => {
    let end: (result: Record<string, unknown>) => void = () => undefined
    const ran = h.hook('tool.call', { tool: 'Bash' })(h.engine, CALL, beneath(() => new Promise((resolve) => (end = resolve)), plugins))
    await h.settle()
    return {
      end: async () => {
        end({ text: OUTPUT })
        await ran
        await h.settle()
      },
    }
  }
  /** A model's row kept through the bridge's hook, these plugins' links settled beneath it. */
  const rowBeneath = (h: Harness, plugins: string[], options: Beneath = {}) =>
    h.append(
      'response',
      { type: 'assistant', role: 'assistant', content: [{ type: 'text', text: 'hi' }] },
      { origin: { kind: 'model', model: 'm' }, next: beneath(async (inner: Record<string, unknown>) => ({ message: inner.message, uuid: inner.uuid }), plugins, options) },
    )
  const posted = (h: Harness) => JSON.stringify(h.posts.map((p) => p.events))
  const whole = [expect.objectContaining({ phase: 'call', input: { command: CALL.command } }), expect.objectContaining({ phase: 'result', text: OUTPUT })]
  const expectSafe = (h: Harness) => {
    expect(h.ofType('tool')).toEqual(whole)
    expect(h.logs).not.toContain(OFF_LINE)
    expect(h.children[0]!.killed).toBe(false)
  }
  /** Off: said once per transition, as a toast and a debug line; the child it had, stopped. */
  const expectOff = (h: Harness, transitions = 1) => {
    expect(h.logs.filter((l) => l === OFF_LINE)).toHaveLength(transitions)
    expect(h.toasts.filter((t) => t === OFF_LINE)).toHaveLength(transitions)
    expect(h.children.at(-1)!.killed).toBe(true)
  }
  /** Back on: said once per transition; a new child for the session, as a reload starts one. */
  const expectOn = (h: Harness, transitions = 1) => {
    expect(h.logs.filter((l) => l === ON_LINE)).toHaveLength(transitions)
    expect(h.toasts.filter((t) => t === ON_LINE)).toHaveLength(transitions)
    expect(h.children.at(-1)!.killed).toBe(false)
  }
  /** The newest child says hello under a nonce of its own; what it is posted from then on. */
  const greetNewest = async (h: Harness, nonce: string) => {
    const at = h.posts.length
    h.children.at(-1)!.write(hello(SID, SOCK, undefined, nonce))
    await h.settle()
    return () => h.posts.slice(at)
  }

  test('the off line says what to set, in the words the spec gives', () => {
    expect(OFF_LINE).toBe(
      'sminos: the bridge is off — sminos must load outside devcloud and cua; set prependPlugins in ~/.claude/settings.json to ["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]',
    )
  })

  // The design's table (§4), row by row, and the stale marker pinned below
  // it: each the first verdict, from the session's first call.
  const table: [string, Parameters<typeof harness>[0], string[], 'safe' | 'off'][] = [
    ["devcloud's guard loaded (its live marker), devcloud beneath", { marker: LIVE_MARKER }, ['doperpowers', 'devcloud'], 'safe'],
    ["devcloud's guard loaded, no devcloud beneath", { marker: LIVE_MARKER }, ['doperpowers'], 'off'],
    ["cua's copy loaded (no marker, cua enabled), cua beneath", { cua: true }, ['doperpowers', 'cua'], 'safe'],
    ["cua's copy loaded, no cua beneath", { cua: true }, ['doperpowers'], 'off'],
    ['no guard loaded (no marker, cua not enabled), nothing beneath', {}, [], 'safe'],
    ['no guard loaded, anything beneath', {}, ['doperpowers', 'devcloud', 'cua'], 'safe'],
    ['a stored marker (version 1, which outlives an older devcloud), cua not enabled, no devcloud beneath', { marker: STORED_MARKER }, ['doperpowers'], 'safe'],
    ["a stored marker with cua enabled reads as cua's row: no cua beneath", { marker: STORED_MARKER, cua: true }, ['doperpowers'], 'off'],
    ["a stored marker with cua enabled reads as cua's row: cua beneath", { marker: STORED_MARKER, cua: true }, ['doperpowers', 'cua'], 'safe'],
    ["devcloud's live marker with cua enabled (cua's copy stands down): devcloud beneath alone", { marker: LIVE_MARKER, cua: true }, ['devcloud'], 'safe'],
    // Exactly the two keys devcloud answers, as cua's own check reads them: anything else is no live marker.
    ['a marker at version 0 with a key devcloud never answers, cua not enabled, no devcloud beneath', { marker: { value: { owner: 'devcloud', version: 1, extra: true }, version: 0 } }, ['doperpowers'], 'safe'],
  ]
  for (const [name, options, plugins, verdict] of table) {
    test(`${name}: ${verdict}`, async () => {
      const h = harness({ ...options, verdictPending: true })
      await h.ready()
      await callBeneath(h, plugins)
      await h.settle()
      if (verdict === 'safe') {
        expectSafe(h)
      } else {
        // The call's events waited for the verdict, which dropped them.
        expect(h.ofType('tool')).toEqual([])
        expect(posted(h)).not.toContain(CALL.command)
        expectOff(h)
      }
    })
  }

  test("a kept row decides as a call does, so the session's first row decides before its first call", async () => {
    const safe = harness({ marker: LIVE_MARKER, verdictPending: true })
    await safe.ready()
    await rowBeneath(safe, ['doperpowers', 'devcloud'])
    await callBeneath(safe, ['doperpowers', 'devcloud'])
    await safe.settle()
    expectSafe(safe)
    const off = harness({ marker: LIVE_MARKER, verdictPending: true })
    await off.ready()
    await rowBeneath(off, ['doperpowers'])
    expectOff(off)
    const posts = off.posts.length
    await callBeneath(off, ['doperpowers'])
    await off.settle()
    expect(off.posts.length).toBe(posts)
  })

  test("a row's notice goes out before its dispatch is judged: the guard reads never delay the notices' write order", async () => {
    const h = harness()
    await h.ready()
    const release = h.holdGuardReads()
    const kept = rowBeneath(h, ['doperpowers'])
    await h.settle()
    expect(h.ofType('block-row').length + h.ofType('row-seen').length).toBe(1)
    release()
    await kept
  })

  test('until the first verdict a tool event waits, and every event behind it; a safe verdict posts them whole, in order', async () => {
    const h = harness({ verdictPending: true })
    await h.ready()
    await h.turn('t1')
    await h.settle()
    const call = await runningBeneath(h, [])
    h.timers.find((t) => t.kind === 'every')!.fn()
    await h.settle()
    // The turn went out before the call; the call's event, and the heartbeat behind it, wait.
    expect(h.ofType('turn')).toHaveLength(1)
    expect(h.ofType('tool')).toEqual([])
    expect(h.ofType('heartbeat')).toEqual([])
    await rowBeneath(h, [])
    expect(h.events().flatMap((e) => (e.type === 'tool' || e.type === 'heartbeat' ? [e.type] : []))).toEqual(['tool', 'heartbeat'])
    expect(h.ofType('tool')).toEqual([whole[0]])
    await call.end()
    expectSafe(h)
  })

  test('a first verdict of off drops what waits: no tool event is posted, the line is said once, and no child is started while it stands', async () => {
    const h = harness({ marker: LIVE_MARKER, verdictPending: true })
    await h.ready()
    const call = await runningBeneath(h, ['doperpowers'])
    await rowBeneath(h, ['doperpowers'])
    expectOff(h)
    await call.end()
    expect(h.ofType('tool')).toEqual([])
    expect(posted(h)).not.toContain(CALL.command)
    expect(posted(h)).not.toContain(OUTPUT)
    // No heartbeat posted, and no child again: not when it ends, not at a session start.
    for (const t of h.timers.filter((t) => t.kind === 'every')) {
      t.fn()
    }
    h.children[0]!.end()
    await h.settle()
    await h.fire(1_000)
    await h.start()
    expect(h.ofType('heartbeat')).toEqual([])
    expect(h.children).toHaveLength(1)
  })

  test('a native question before the first verdict is raised as the engine gave it: no guard restores into one', async () => {
    const h = harness({ verdictPending: true })
    await h.ready()
    const questions = [{ question: 'Which?', header: 'Pick', options: [{ label: 'a', description: 'A' }, { label: 'b', description: 'B' }], multiSelect: false }]
    void h.permission('AskUserQuestion', { questions })
    const poll = await h.nextPoll()
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ tool: 'AskUserQuestion', input: { questions } })])
    poll.respond(410)
  })

  test("until the first verdict a permission's input is not raised (the dialog is the terminal's); once safe, the next one is", async () => {
    const h = harness({ verdictPending: true })
    await h.ready()
    await h.turn('t1')
    const first = await h.called('tu1', 'Bash', { command: 'ls' })
    expect(await h.permission('Bash', { command: 'ls' })).toEqual({})
    expect(h.ofType('raised')).toEqual([])
    expect(h.polls).toEqual([])
    // The call's own dispatch settles safe (no guard is loaded).
    await first.end()
    await h.settle()
    await h.called('tu2', 'Bash', { command: 'pwd' })
    void h.permission('Bash', { command: 'pwd' })
    const poll = await h.nextPoll()
    expect(h.ofType('raised')).toEqual([expect.objectContaining({ request: 'tu2', tool: 'Bash', input: { command: 'pwd' } })])
    poll.respond(410)
  })

  test('the verdict is read on every dispatch: a guard loaded outside a living instance turns it off at the next one', async () => {
    const h = harness()
    await h.ready()
    await callBeneath(h, [])
    await h.settle()
    expectSafe(h)
    // devcloud enabled mid-session on an unplaced machine: its module loads
    // outside this instance, which the reload does not replace.
    h.setMarker(LIVE_MARKER)
    await rowBeneath(h, ['doperpowers'])
    expectOff(h)
  })

  test('outside a loaded guard it stays off across every dispatch: nothing posted, no child started, said once', async () => {
    const h = harness({ marker: LIVE_MARKER, verdictPending: true })
    await h.ready()
    await rowBeneath(h, ['doperpowers'])
    const posts = h.posts.length
    for (let i = 0; i < 5; i++) {
      await rowBeneath(h, ['doperpowers'])
      await callBeneath(h, ['doperpowers'])
      await h.turn(`t${i}`)
      for (const t of h.timers.filter((t) => t.kind === 'every')) {
        t.fn()
      }
    }
    // A question too goes to the terminal unraised while the bridge is off.
    expect(await h.permission('AskUserQuestion', { questions: [] })).toEqual({})
    await h.settle()
    expect(h.posts.length).toBe(posts)
    expect(h.children).toHaveLength(1)
    expectOff(h)
  })

  test('a guard loaded while a call was in flight reads off at its end, and the next dispatch, beneath it, turns the bridge back on as a reload would', async () => {
    const h = harness()
    await h.ready()
    // The call's chain was taken before devcloud loaded: its trace has no devcloud.
    const call = await runningBeneath(h, ['doperpowers'])
    h.setMarker(LIVE_MARKER)
    await call.end()
    expectOff(h)
    expect(h.ofType('tool').filter((e) => e.phase === 'result')).toEqual([])
    // The next row's chain has devcloud beneath: safe, and it began after the off.
    await rowBeneath(h, ['doperpowers', 'devcloud'])
    expectOn(h)
    expect(h.children).toHaveLength(2)
    expect(h.children[1]!.argv).toEqual(['/plug/skills/sminos/scripts/sminos', 'bridge', '--session', SID])
    // A new child, a new nonce: what an old instance still posts is turned away.
    const after = await greetNewest(h, 'n1')
    expect(after().slice(0, 2).map((p) => p.events.map((e) => e.type))).toEqual([['session'], ['resync']])
    await callBeneath(h, ['doperpowers', 'devcloud'])
    await h.settle()
    expect(after().every((p) => p.nonce === 'n1')).toBe(true)
    expect(after().flatMap((p) => p.events).filter((e) => e.type === 'tool')).toEqual(whole)
  })

  test("cua enabled in the settings but not yet loaded reads off; the reload that seats cua beneath turns the bridge back on", async () => {
    const h = harness({ cua: true, verdictPending: true })
    await h.ready()
    // The settings name cua before its module is in the chain: the leg reads intent.
    await rowBeneath(h, ['doperpowers'])
    await rowBeneath(h, ['doperpowers'])
    expectOff(h)
    // /reload-plugins: cua's module loads in tier user, beneath the bridge; its command rows say so.
    await rowBeneath(h, ['doperpowers', 'cua'])
    expectOn(h)
    const after = await greetNewest(h, 'n1')
    await callBeneath(h, ['doperpowers', 'cua'])
    await h.settle()
    expect(after().flatMap((p) => p.events).filter((e) => e.type === 'tool')).toEqual(whole)
  })

  test("only a guard seen beneath turns an off bridge back on: cua disabled in the settings, its module still outside, keeps it off", async () => {
    const h = harness({ cua: true, verdictPending: true })
    await h.ready()
    await rowBeneath(h, ['doperpowers'])
    expectOff(h)
    const posts = h.posts.length
    // The person disables cua without reloading: its module stays loaded, outside the bridge.
    h.setCua(false)
    for (let i = 0; i < 5; i++) {
      await rowBeneath(h, ['doperpowers'])
      await callBeneath(h, ['doperpowers'])
    }
    await h.settle()
    expect(h.logs).not.toContain(ON_LINE)
    expect(h.children).toHaveLength(1)
    expect(h.posts.length).toBe(posts)
    expectOff(h)
  })

  test('a dispatch that began before the last transition and reads off changes nothing, and posts nothing of its own', async () => {
    const h = harness()
    await h.ready()
    // Calls A and B are in flight when devcloud loads: neither chain has it.
    let endA: (r: Record<string, unknown>) => void = () => undefined
    let endB: (r: Record<string, unknown>) => void = () => undefined
    const a = h.hook('tool.call', { tool: 'Bash' })(h.engine, { ...CALL, tool_use_id: 'tuA' }, beneath(() => new Promise((resolve) => (endA = resolve)), ['doperpowers']))
    const b = h.hook('tool.call', { tool: 'Bash' })(h.engine, { ...CALL, tool_use_id: 'tuB' }, beneath(() => new Promise((resolve) => (endB = resolve)), ['doperpowers']))
    await h.settle()
    h.setMarker(LIVE_MARKER)
    endA({ text: OUTPUT })
    await a
    await h.settle()
    expectOff(h)
    await rowBeneath(h, ['doperpowers', 'devcloud'])
    expectOn(h)
    const after = await greetNewest(h, 'n1')
    endB({ text: 'B output' })
    await b
    await h.settle()
    // No second off, and B's result, read outside the guard, is not posted.
    expect(h.toasts.filter((t) => t === OFF_LINE)).toHaveLength(1)
    expectOn(h)
    expect(h.children).toHaveLength(2)
    expect(JSON.stringify(after().map((p) => p.events))).not.toContain('B output')
  })

  test("going off leaves a question's dialog to settle as it does: an async ask answered through it settles answered with its winner, nothing stranded across the recovery", async () => {
    const FRUIT = { question: 'Which fruit?', header: 'Fruit', multiSelect: false, options: [{ label: 'Apple', description: 'a' }, { label: 'Mango', description: 'm' }] }
    const h = harness()
    await h.ready()
    await h.turn('t1')
    onAskNote({ kind: 'open', id: 'toolu_a1', questions: [FRUIT] })
    // A press on the ask's [ answer ] opened this dialog.
    await h.check('toolu_plugin_9', 'AskUserQuestion', { questions: [FRUIT] })
    const answer = h.permission('AskUserQuestion', { questions: [FRUIT] })
    const poll = await h.nextPoll()
    h.setMarker(LIVE_MARKER)
    await rowBeneath(h, ['doperpowers'])
    expectOff(h)
    // The person answers at the terminal; the ask mod's note follows the
    // dialog's answer, and the engine's record of who decided follows it.
    poll.respond(410, { reason: 'terminal' })
    await answer
    onAskNote({ kind: 'answered', id: 'toolu_a1', dialog: 'toolu_plugin_9' })
    await h.settle()
    await h.recorded('toolu_plugin_9', 'user_temporary', 'accept', 'AskUserQuestion')
    await rowBeneath(h, ['doperpowers', 'devcloud'])
    expectOn(h)
    const after = await greetNewest(h, 'n1')
    const resync = after().flatMap((p) => p.events).find((e) => e.type === 'resync')!
    expect(resync.pending).toEqual([])
    expect(resync.settled).toEqual([
      expect.objectContaining({ request: 'toolu_plugin_9', winner: 'terminal', outcome: 'answered', by: 'terminal' }),
      expect.objectContaining({ request: 'toolu_a1', winner: 'terminal', outcome: 'answered', by: 'terminal' }),
    ])
  })

  test('going off withdraws a pending permission, whose input came through the guard', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.called('tu1', 'Bash', { command: 'ls' })
    void h.permission('Bash', { command: 'ls' })
    const poll = await h.nextPoll()
    h.setMarker(LIVE_MARKER)
    await rowBeneath(h, ['doperpowers'])
    expectOff(h)
    poll.respond(410)
    await rowBeneath(h, ['doperpowers', 'devcloud'])
    const after = await greetNewest(h, 'n1')
    const resync = after().flatMap((p) => p.events).find((e) => e.type === 'resync')!
    expect(resync.pending).toEqual([])
    expect(resync.settled).toEqual([expect.objectContaining({ request: 'tu1', outcome: 'withdrawn', by: 'bridge' })])
  })

  test('a permission whose hooks beneath were running when the bridge turned off is not raised: nothing pending to resync once it is back on', async () => {
    const h = harness()
    await h.ready()
    await h.turn('t1')
    await h.called('tu1', 'Bash', { command: 'ls' })
    // The settings hooks beneath the bridge's PermissionRequest hook run while devcloud loads outside it.
    let decide: (result: Record<string, unknown>) => void = () => undefined
    const answered = h.hook('classic.PermissionRequest', { hook_event_name: 'PermissionRequest' })(
      h.engine,
      { hook_event_name: 'PermissionRequest', tool_name: 'Bash', tool_input: { command: 'ls' }, session_id: SID, transcript_path: '/t', cwd: '/w' },
      Object.assign(() => new Promise((resolve) => (decide = resolve)), { signal: new AbortController().signal }),
    ) as Promise<Record<string, unknown>>
    await h.settle()
    h.setMarker(LIVE_MARKER)
    await rowBeneath(h, ['doperpowers'])
    expectOff(h)
    decide({})
    await h.settle()
    expect(h.polls).toEqual([])
    await rowBeneath(h, ['doperpowers', 'devcloud'])
    expectOn(h)
    const after = await greetNewest(h, 'n1')
    const resync = after().flatMap((p) => p.events).find((e) => e.type === 'resync')!
    expect(resync.pending).toEqual([])
    expect(await answered).toEqual({})
  })

  test('a dispatch that began before the off and reads safe does not turn the bridge back on', async () => {
    const h = harness()
    await h.ready()
    const call = await runningBeneath(h, ['doperpowers', 'devcloud'])
    h.setMarker(LIVE_MARKER)
    await rowBeneath(h, ['doperpowers'])
    expectOff(h)
    await call.end()
    expect(h.logs).not.toContain(ON_LINE)
    expect(h.children).toHaveLength(1)
  })

  test('off and on again, then off again: each transition said once, and a /clear while off starts no child', async () => {
    const h = harness({ marker: LIVE_MARKER, verdictPending: true })
    await h.ready()
    await rowBeneath(h, ['doperpowers'])
    expectOff(h)
    // A /clear while off: the new session is found, but no child is started for it.
    await h.hook('session.end', {})(h.engine, { reason: 'clear', sessionId: SID }, async () => ({}))
    await h.settle()
    const NEW = '6c000002-0000-4000-8000-00000000006c'
    h.setSession(NEW)
    for (const t of h.timers.filter((t) => t.kind === 'after' && !t.cancelled)) {
      t.cancelled = true
      t.fn()
    }
    await h.settle()
    expect(h.children).toHaveLength(1)
    // Back on only through a safe dispatch, for the session the /clear moved to.
    await rowBeneath(h, ['doperpowers', 'devcloud'])
    expectOn(h)
    expect(h.children[1]!.argv).toEqual(['/plug/skills/sminos/scripts/sminos', 'bridge', '--session', NEW])
    await rowBeneath(h, ['doperpowers'])
    expectOff(h, 2)
    expect(h.logs.filter((l) => l === ON_LINE)).toHaveLength(1)
  })

  test("off on a call's own dispatch: its result is never posted (its call event went out before it ran: the window §4 accepts)", async () => {
    const h = harness()
    await h.ready()
    h.setMarker(LIVE_MARKER)
    await callBeneath(h, ['doperpowers'])
    await h.settle()
    expect(h.ofType('tool').filter((e) => e.phase === 'result')).toEqual([])
    expect(posted(h)).not.toContain(OUTPUT)
    expectOff(h)
  })

  test('a guard loaded beneath a living instance (a placed machine) leaves it safe', async () => {
    const h = harness()
    await h.ready()
    h.setMarker(LIVE_MARKER)
    await rowBeneath(h, ['doperpowers', 'devcloud'])
    await callBeneath(h, ['doperpowers', 'devcloud'])
    await h.settle()
    expectSafe(h)
  })

  test('only a trace that reaches the engine says a guard is missing: one cut short by a link beneath that answered itself decides nothing', async () => {
    const h = harness({ marker: LIVE_MARKER, verdictPending: true })
    await h.ready()
    // A plugin's own tool answered by its hook, a row a hook refused: what lies beneath that link is not listed.
    await callBeneath(h, ['doperpowers'], { short: true })
    await h.settle()
    expect(h.logs).not.toContain(OFF_LINE)
    expect(h.ofType('tool')).toEqual([])
    // Cut short at the guard itself (it refused the call), the trace names it: safe, and what waited goes out.
    await callBeneath(h, ['doperpowers', 'devcloud'], { short: true })
    await h.settle()
    expect(h.ofType('tool')).toEqual([...whole, ...whole])
    expect(h.logs).not.toContain(OFF_LINE)
  })

  test("a dispatch a guard's own plugin raised says nothing of that guard, whose hooks do not run on it", async () => {
    const h = harness({ cua: true, verdictPending: true })
    await h.ready()
    // cua's /secret appends its note: cua's hooks are not in that row's chain.
    await rowBeneath(h, ['doperpowers'], { origin: 'cua' })
    expect(h.logs).not.toContain(OFF_LINE)
    await rowBeneath(h, ['doperpowers'])
    expectOff(h)
  })

  test("which guard is loaded is read only when the links beneath do not name both: devcloud's marker, then cua in the user settings", async () => {
    const both = harness({ verdictPending: true })
    await both.ready()
    await callBeneath(both, ['doperpowers', 'devcloud', 'cua'])
    await both.settle()
    expect(both.guardReads).toEqual([])
    expectSafe(both)
    const neither = harness({ verdictPending: true })
    await neither.ready()
    await rowBeneath(neither, ['doperpowers'])
    expect(neither.guardReads).toEqual([
      { op: 'state.get', args: { plugin: 'devcloud', key: 'secrets-guard' } },
      { op: 'settings.read', args: { source: 'user' } },
    ])
  })

  test('a read that fails decides nothing: the debug log says why each time, a toast once for the module instance', async () => {
    const h = harness({ stateFails: true, verdictPending: true })
    await h.ready()
    await callBeneath(h, ['doperpowers'])
    await rowBeneath(h, ['doperpowers'])
    await h.settle()
    expect(h.logs).not.toContain(OFF_LINE)
    expect(h.ofType('tool')).toEqual([])
    expect(h.logs.filter((l) => l.includes('$.state.get: the host did not answer'))).toHaveLength(2)
    expect(h.toasts).toHaveLength(1)
    expect(h.toasts[0]).toContain('cannot read which secrets guard is loaded')
    expect(h.toasts[0]).toContain('$.state.get: the host did not answer')
  })
})
