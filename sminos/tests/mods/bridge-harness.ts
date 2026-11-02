import type { EngineInterface, On } from 'claude-code'

import { PLUGIN } from '../../hooks/mods/ask'
import { registerBridge, resetBridge } from '../../hooks/mods/bridge'

/**
 * The bridge's test harness, shared by the bridge's tests (bridge.test.ts) and
 * the fork agent's (bridge-ask.test.ts): the hooks as register.tsx registers
 * them, an engine of plain records, and the child's side of the protocol.
 */

export const SID = '5b000001-0000-4000-8000-00000000005b'
export const SOCK = `/tmp/s/bridge/${SID}.sock`
export const NONCE = 'n0'
export const hello = (session = SID, socket = SOCK, kept?: Record<string, unknown>, nonce = NONCE, seed?: Record<string, string>) =>
  `${JSON.stringify({ op: 'hello', session, pid: 7, socket, protocol: 1, nonce, ...(kept !== undefined && { kept }), ...(seed !== undefined && { seed }) })}\n`
export const line = (obj: Record<string, unknown>) => `${JSON.stringify(obj)}\n`
/** The versions of one host's `$.state` (a `sessionState` map), whichever harness reads it. */
const stateVersionsBy = new WeakMap<Map<string, unknown>, Map<string, number>>()
const versionsOf = (kept: Map<string, unknown>) => {
  const versions = stateVersionsBy.get(kept) ?? new Map<string, number>()
  stateVersionsBy.set(kept, versions)
  return versions
}
/** The child's command line as the mod starts it: its session, and the process's launch the harness's `$.state` holds (O12 M7). */
export const childArgv = (h: { sessionState: Map<string, unknown> }, session = SID) => [
  '/plug/skills/sminos/scripts/sminos',
  'bridge',
  '--session',
  session,
  `--launch=${String(h.sessionState.get('launch'))}`,
]
/** A steer's row and a delivered message's, as a wake counts them. */
export const NOTE = {}
export const MESSAGE = (frame?: string) => ({ isDelivery: true, ...(frame !== undefined && { frame }) })
/**
 * A `next` as the engine hands it to a hook, once it settled: `next.trace`
 * lists the links beneath, one per plugin's module, nearest first, and the
 * engine's own entry last, unless a link answered the call itself (`short`);
 * `next.origin` names the plugin that raised the dispatch, the engine when
 * none did. A `next` that names its origin already keeps it.
 */
export const beneath = <T extends object>(next: T, plugins: readonly string[], options: { short?: boolean; origin?: string } = {}) => {
  const links = [...plugins, ...(options.short === true ? [] : ['engine'])]
  const trace = links.map((plugin, i) => ({ index: i + 1, plugin, tier: plugin === 'engine' ? 'core' : 'user', event: 'tool.call', outcome: 'returned', ms: 0, received: {}, returned: undefined }))
  const origin = options.origin === undefined ? { plugin: 'engine', tier: 'core' } : { plugin: options.origin, tier: 'user' }
  return Object.assign(next, { trace }, 'origin' in next && options.origin === undefined ? {} : { origin })
}
/** devcloud's marker as its loaded module answers it (at version 0), and as an older devcloud stored it (version 1), which outlives its module. */
/** The longest body `$.http.fetch` sends, in characters. */
export const ENGINE_BODY_MAX = 4_194_304
export const LIVE_MARKER = { value: { owner: 'devcloud', version: 1 }, version: 0 }
export const STORED_MARKER = { value: { owner: 'devcloud', version: 1 }, version: 1 }

export type Handler = (...args: unknown[]) => unknown
export type Matcher = Record<string, unknown> | undefined
export type Piece = { stream: 'stdout' | 'stderr'; text: string }

/** A child as `$.process.spawn` streams it: the test writes its output and ends it. */
export function fakeChild(argv: readonly string[]) {
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
export function harness(
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
    /**
     * Asked before each `$.state` read or write of this plugin's own key: `fail`
     * makes the call reject (the host did not answer); anything else lets it
     * run, after whatever the function did (another writer's write, say).
     */
    stateFault?: (op: 'get' | 'set', key: string) => 'fail' | undefined
    /** What `$.session.version()` answers; by default 2.1.300's release, with no base. */
    version?: { version: string; base?: string; builtAt?: string }
    /** What `$.command.list()` answers. */
    commands?: Record<string, unknown>[]
    models?: string[]
    configFails?: boolean
    configWait?: Promise<void>
    /** What `$.session.repo()` answers. */
    repo?: { root: string; remote: string | null; internal: boolean; name: string | null } | null
    /** What `$.model.fork` resolves to at once; otherwise each fork waits for the test (`forks`). */
    forkAnswer?: Record<string, unknown>
    /**
     * The host's `$.state` for this plugin's own keys, by key: shared between
     * two harnesses, it is what a reloaded module finds of the one before it.
     */
    sessionState?: Map<string, unknown>
    /** `$.session.send` answers not delivered, with this reason. */
    sendRefuses?: string
    /**
     * doperpowers' read-only fork guard is loaded (setGuard changes it): its
     * `tool.check` answers the bridge's presence query (`$.tool.check` for a
     * Read of FORK_GUARD_PROBE) with FORK_GUARD_PRESENT; without it core
     * answers, `allow`.
     */
    guard?: boolean
    /** `$.agent.spawn` answers `{ deny }` with this reason. */
    spawnDeny?: string
    /**
     * How the child's private gate route (POST /holder, O12 M4a) answers a
     * body: an answer, `hold` (the test settles it, `holderPosts[i].answer`),
     * or `fail` (the request fails, as with no child). By default `ready`,
     * `armed` and `turn` are answered as a live child answers them, and a
     * `wait` is held.
     */
    holderAnswer?: (body: Record<string, unknown>) => { status: number; body?: unknown } | 'hold' | 'fail' | undefined
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
  /** Files `$.fs.read` reads (the session's transcripts; the plugin's manifest). */
  const files: Record<string, string> = { '/plug/.claude-plugin/plugin.json': JSON.stringify({ name: 'sminos', version: '1.7.0' }) }
  /** What `$.fs.stat` finds at a path: its kind, whether it is a link, and where it resolves (itself unless said). */
  const stats: Record<string, { kind: 'file' | 'dir' | 'other'; isLink?: boolean; realPath?: string }> = {}
  const sessionState = options.sessionState ?? new Map<string, unknown>()
  const fault = options.stateFault
  /** Each `$.model.fork`, held until the test settles it. */
  const forks: { prompt: string; resolve: (r: Record<string, unknown>) => void; reject: (e: Error) => void }[] = []
  /** Each `$.command.run`, held until the test settles it. */
  const runs: { args: { command: string; args?: string }; resolve: (r: Record<string, unknown>) => void; reject: (e: Error) => void }[] = []
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
  /** What `$.session.messages()` answers (the rows): `messages` at load, then what setRows set. */
  let sessionRows: unknown[] = options.messages ?? []
  let isGuardLoaded = options.guard === true
  /** Each `$.agent.spawn`, in order. */
  const spawns: Record<string, unknown>[] = []
  /** Each `$.tool.check` query, in order. */
  const queries: Record<string, unknown>[] = []
  /** How many times the mod read `$.agent.list()`. */
  let agentLists = 0
  /** The host's `$.state` versions for this plugin's own keys: each write moves its key's; shared with every harness sharing `sessionState` (one host). */
  const stateVersions = versionsOf(sessionState)
  /** Each POST /holder the mod made on the child's private route, in order, with what `$.state` kept when it was made. */
  const holderPosts: {
    socketPath?: string
    nonce?: string
    body: Record<string, unknown>
    kept: unknown
    answer: (status: number, body?: unknown) => void
    fail: () => void
  }[] = []
  const $ = {
    plugin: { name: PLUGIN, root: '/plug' },
    env: { get: async (name: string) => options.env?.[name] },
    session: {
      id: async () => session,
      model: async () => 'claude-haiku',
      version: async () => options.version ?? { version: '2.1.300' },
      cwd: async () => '/w',
      root: async () => '/w',
      repo: async () => (options.repo === undefined ? null : options.repo),
      surfaces: async () => ['terminal'],
      // As the requests read it (`as: "api"`): the mod's appended rows, unless a test rewound it.
      messages: async (args?: { as?: string }) => {
        if (args?.as !== 'api') {
          return sessionRows
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
      send: async (args: unknown) => {
        calls.push({ op: 'send', args })
        return options.sendRefuses !== undefined ? { isDelivered: false, reason: options.sendRefuses } : { isDelivered: true }
      },
      compact: (args: unknown) => {
        calls.push({ op: 'compact', args })
        return new Promise((resolve, reject) => compactions.push({ args, finish: resolve, fail: reject }))
      },
    },
    model: {
      fork: (request: { prompt: string }) => {
        calls.push({ op: 'fork', args: request })
        return options.forkAnswer !== undefined ? Promise.resolve(options.forkAnswer) : new Promise((resolve, reject) => forks.push({ prompt: request.prompt, resolve, reject }))
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
      list: async () => [{ name: 'Bash', description: '', mcp: false }, { name: 'mcp__probe__hello', description: '', mcp: true }],
      // As the chain answers a query: the guard's tool.check, when it is loaded, answers its probe; core allows.
      check: async (query: { tool: string; input: unknown }) => {
        queries.push(query)
        const isProbe = query.tool === 'Read' && (query.input as { file_path?: unknown } | null)?.file_path === '/dev/null/sminos-fork-guard-probe'
        return isProbe && isGuardLoaded ? { decision: 'deny', reason: 'The read-only fork guard (doperpowers) is loaded.' } : { decision: 'allow' }
      },
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
      spawn: async (args: Record<string, unknown>) => {
        spawns.push(args)
        return options.spawnDeny !== undefined ? { deny: options.spawnDeny } : { model: 'claude-haiku', agentId: `afork${spawns.length}` }
      },
      list: async () => {
        agentLists++
        return listedAgents.map((a) => ({ ...a }))
      },
    },
    config: { list: async () => {
      if (options.configFails) throw new Error('config unavailable')
      await options.configWait
      return [{ key: 'model', label: 'Model', kind: 'choice', value: 'default', provider: { kind: 'engine' }, isLocked: false, options: options.models ?? ['default', 'sonnet', 'opus'] }]
    } },
    command: {
      list: async () => (options.commands ?? []).map((c) => ({ ...c })),
      run: (args: { command: string; args?: string }) => {
        calls.push({ op: 'command.run', args })
        return new Promise((resolve, reject) => runs.push({ args, resolve, reject }))
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
          if (url === 'http://holder/holder') {
            const body = JSON.parse(init.body ?? '{}') as Record<string, unknown>
            const answer = (status: number, answered?: unknown) => resolve({ status, ok: status < 300, headers: {}, text: answered === undefined ? '' : JSON.stringify(answered) })
            const fail = () => reject(new Error('connect ENOENT'))
            holderPosts.push({ socketPath: init.socketPath, nonce: init.headers?.['x-bridge-nonce'], body, kept: structuredClone(sessionState.get('holder')), answer, fail })
            const given = options.holderAnswer?.(body)
            const how = given ?? (body.kind === 'wait' ? 'hold' : { status: 200, body: body.kind === 'ready' ? { ok: true, lane: 'match', epoch: null } : body.kind === 'armed' ? { ok: true, sent: 1, waiting: 0 } : { ok: true } })
            if (how === 'fail') {
              fail()
            } else if (how !== 'hold') {
              answer(how.status, how.body)
            }
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
        if (ref.plugin === PLUGIN) {
          if (options.stateFault?.('get', ref.key) === 'fail') {
            throw new Error('$.state.get: the host did not answer')
          }
          return sessionState.has(ref.key) ? { value: sessionState.get(ref.key), version: stateVersions.get(ref.key) ?? 1 } : { value: undefined, version: 0 }
        }
        guardReads.push({ op: 'state.get', args: ref })
        await readGate
        if (options.stateFails) {
          throw new Error('$.state.get: the host did not answer')
        }
        return ref.plugin === 'devcloud' && ref.key === 'secrets-guard' ? marker : { value: undefined, version: 0 }
      },
      set: async (ref: { plugin: string; key: string }, value: unknown, options?: { ifVersion?: number }) => {
        if (ref.plugin === PLUGIN && fault?.('set', ref.key) === 'fail') {
          throw new Error('$.state.set: the host did not answer')
        }
        // As the host: a write naming a version that no longer stands is refused.
        const at = sessionState.has(ref.key) ? (stateVersions.get(ref.key) ?? 1) : 0
        if (options?.ifVersion !== undefined && options.ifVersion !== at) {
          return { isSet: false, version: at }
        }
        sessionState.set(ref.key, value)
        stateVersions.set(ref.key, at + 1)
        return { isSet: true, version: at + 1 }
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
      stat: async (path: string, options?: { resolve?: boolean }) => {
        const found = stats[path]
        if (found === undefined) {
          throw new Error(`ENOENT: ${path}`)
        }
        return { kind: found.kind, size: 80, mtimeMs: 0, isLink: found.isLink === true, ...(options?.resolve === true && { realPath: found.realPath ?? path }) }
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
  const turn = async (turnId: string, agentId?: string, text = 'go') =>
    hook('turn.start', { turnId })(engine, { turnId, text, ...(agentId !== undefined && { agentId }) }, async () => ({ turnId }))
  /** A prompt submitted, through the prompt.submit hooks, stamped with the engine's origin `kind` (`turnId`: the turn running when it came). */
  const submit = async (text: string, kind: string, extra: { turnId?: string; entered?: Record<string, unknown> } = {}) => {
    const e = { text, wait: false, origin: { kind }, ...(extra.turnId !== undefined && { turnId: extra.turnId }) }
    const entered = await (hook('prompt.submit', { text })(engine, e, async () => extra.entered ?? { text }) as Promise<unknown>)
    await settle()
    return entered
  }
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
  /** The classic PermissionRequest hooks for a call, with the engine's `suggestions` if any and the loop's permission `mode`; the settings hooks beneath answer `beneath`. */
  const permission = (tool: string, input: unknown, agentId?: string, beneath: Record<string, unknown> = {}, suggestions?: unknown, mode?: string) =>
    hook('classic.PermissionRequest', { hook_event_name: 'PermissionRequest' })(
      engine,
      {
        hook_event_name: 'PermissionRequest',
        tool_name: tool,
        tool_input: input,
        session_id: SID,
        transcript_path: '/t',
        cwd: '/w',
        ...(agentId !== undefined && { agent_id: agentId }),
        ...(suggestions !== undefined && { permission_suggestions: suggestions }),
        ...(mode !== undefined && { permission_mode: mode }),
      },
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
    stats,
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
    forks,
    sessionState,
    runs,
    appends,
    submits,
    conversation,
    requests,
    command,
    turn,
    submit,
    complete,
    posts,
    holderPosts,
    /** The private route's posts of these kinds, their bodies, in the order made. */
    holderBodies: (...kinds: string[]) => holderPosts.map((p) => p.body).filter((b) => kinds.length === 0 || kinds.includes(String(b.kind))),
    timers,
    logs,
    toasts,
    guardReads,
    /** Another writer's write of this plugin's key (a module instance before this one): the version moves as with any write. */
    writeState: (key: string, value: unknown) => {
      stateVersions.set(key, (sessionState.has(key) ? (stateVersions.get(key) ?? 1) : 0) + 1)
      sessionState.set(key, value)
    },
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
    setRows: (next: unknown[]) => (sessionRows = next),
    setGuard: (isLoaded: boolean) => (isGuardLoaded = isLoaded),
    spawns,
    queries,
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
