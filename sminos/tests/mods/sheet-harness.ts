import type { EngineInterface, On } from 'claude-code'

import { registerAsk, registerAskBand, resetAsk } from '../../hooks/mods/ask'
import { SHEET_TOOL } from '../../hooks/mods/sheet-model'
import type { Probe, View } from '../../hooks/mods/sheet-model'
import { registerSheet, registerSheetBand, resetSheet } from '../../hooks/mods/sheet'

/**
 * The question sheet's test harness, shared by sheet.test.ts (M3: the choice,
 * a call, the start), sheet-delivery.test.ts (M4: the routes, landing) and
 * sheet-drawing.test.ts (M5: the band, the rows, the import): the hooks in
 * register.tsx's order (the sheet's band, the ask's, the sheet, the ask) on
 * an engine of plain records, whose process runs are the command answering
 * as each test scripts it.
 */

type Handler = (...args: unknown[]) => unknown
type Matcher = Record<string, unknown> | undefined
export type Origin = { plugin: string; tier: string }

export const MODEL: Origin = { plugin: 'engine', tier: 'core' }
export const HOME = '/home/sm'
export const COMMAND = '/plug/skills/sminos/scripts/sminos'
export const S1 = '5eed0000-0000-4000-8000-0000000000c1'
export const S2 = '5eed0000-0000-4000-8000-0000000000c2'
/** A record's witness as `sminos sheet witness` prints it (its identity, the start it had), and another record's. */
export const W1 = `16777220:4242:${'a'.repeat(32)}:n-before`
export const W2 = `16777220:4242:${'b'.repeat(32)}:`
/** The pid of the engine process the harness stands for. */
export const ENGINE_PID = '31337'
export const ALIVE: Probe = { record: false, open: 0, pending: 0, queued: 0, surface: { name: 'standin', url: 'http://sheet.localhost:47590', reach: 'local' }, surfaces: 1 }

export const view = (over: Partial<View> = {}): View => ({
  seq: 1,
  offset: 0,
  nextId: 1,
  open: [],
  pending: [],
  pendingCount: 0,
  owedAcrossStop: 0,
  closed: {},
  answered: [],
  answeredCount: 0,
  ready: [],
  surface: ALIVE.surface,
  surfaces: 1,
  ...over,
})

/** A step's answer, as the command prints it. */
export const ok = (seq: number, effects: Record<string, unknown> = {}, over: Partial<View> = {}) =>
  JSON.stringify({ ok: true, seq, view: view({ seq, ...over }), effects: { applied: [], skipped: 0, verdicts: {}, owed: 0, ...effects } })

export type StepEvent = Record<string, unknown> & { event: string; session?: string; call?: { callId: string; floor?: number }; start?: Record<string, unknown>; acked?: string[]; agents?: unknown }
/** What a scripted step does: print `stdout`, or reject (the process did not start or ran out of time). */
export type StepScript = (event: StepEvent, n: number) => string | Promise<string>

/**
 * A registrar that keeps the hooks of register.tsx's order (the sheet's band,
 * the ask's, the sheet, the ask), and an engine of plain records whose process runs are
 * the command answering as each test scripts it.
 */
export function harness(
  options: {
    env?: Record<string, string>
    isInteractive?: boolean
    session?: string
    kept?: Map<string, unknown>
    probe?: Probe
    /** A record's state.json there: the choice probes it. */
    record?: boolean
    step?: StepScript
    /** What `$.tool.check` answers for a Read of a path; allow otherwise. */
    checks?: Record<string, unknown>
    /** What `$.tool.call` answers for a Read of a path; a one-line text otherwise. */
    reads?: Record<string, unknown>
    agents?: { id: string; description: string; type: string; status: string }[]
    /** The conversation the engine holds; rejects when absent (C0's P5). */
    messages?: { rows: { role: string; text: string; toolUses: { tool: string; text?: string }[] }[]; api: { role: string; content: unknown }[] }
    /** Awaited before the conversation's api form is answered: a read the test holds. */
    apiRead?: () => Promise<void>
    files?: Record<string, string>
    remove?: number
    /** What `sminos sheet witness` answers, the n-th time (a record's identity at a /clear); W1 otherwise. */
    witness?: (n: number) => { exitCode: number; stdout?: string }
    /** The engine's pid as `$.process.hookEnv` gives it (`CLAUDE_PID`); ENGINE_PID otherwise, none when null. */
    enginePid?: string | null
    /** What `$.prompt.submit` answers for a text (the idle route); `{ text }` otherwise. */
    submit?: (text: string) => unknown
    /** What `$.session.send` answers for a send to an agent; delivered otherwise. */
    send?: (agentId: string, text: string) => unknown
    /** What a program other than the command answers (a transcript's search): its exit code and output. */
    exec?: (argv: readonly string[]) => { exitCode: number; stdout: string; isStdoutTruncated?: boolean } | Promise<{ exitCode: number; stdout: string; isStdoutTruncated?: boolean }>
    /** The clock (`$.clock.now`), in milliseconds since the epoch. */
    now?: number
    /** Whether the n-th `$.state.set` of a key (`plugin.key`) is refused; none is otherwise. */
    refuseSet?: (key: string, n: number) => boolean
    /** What `sminos sheet log` (the projection) answers; exit 0 otherwise. */
    log?: (n: number) => { exitCode: number; stderr?: string } | Promise<{ exitCode: number; stderr?: string }>
  } = {},
) {
  const hooks: { event: string; matcher: Matcher; handler: Handler; onFailure?: Handler }[] = []
  const on = ((event: string, ...rest: unknown[]) => {
    const handler = rest[rest.length - 1] as Handler
    const matcher = rest.length > 1 ? (rest[0] as Matcher) : undefined
    const hook: (typeof hooks)[number] = { event, matcher, handler }
    hooks.push(hook)
    return { catch: (onFailure: Handler) => void (hook.onFailure = onFailure) }
  }) as unknown as On
  const calls: { op: string; args: unknown }[] = []
  const steps: StepEvent[] = []
  const files = new Map(Object.entries(options.files ?? {}))
  const kept = options.kept ?? new Map<string, unknown>()
  let conversation = options.messages
  const timers: (() => void)[] = []
  /** `$.clock.after` callbacks not yet run: a hop runs them, each once. */
  const afters: (() => void)[] = []
  const submits: string[] = []
  const sends: { agentId: string; text: string }[] = []
  let session = options.session ?? S1
  let projections = 0
  let witnesses = 0
  const sets = new Map<string, number>()
  const env: Record<string, string> = { SMINOS_HOME: HOME, ...options.env }
  const $ = {
    plugin: { root: '/plug', name: 'sminos' },
    env: { get: async (name: string) => env[name] },
    session: {
      id: async () => session,
      cwd: async () => '/work',
      send: async ({ to, text }: { to: { agentId: string }; text: string }) => {
        calls.push({ op: 'session.send', args: { to, text } })
        sends.push({ agentId: to.agentId, text })
        return options.send !== undefined ? options.send(to.agentId, text) : { isDelivered: true }
      },
      messages: async (opts?: { as?: string }) => {
        calls.push({ op: 'session.messages', args: opts })
        if (opts?.as === 'api' && options.apiRead !== undefined) await options.apiRead()
        if (conversation === undefined) throw new Error('not available in this mode: no session is bound in this process')
        return opts?.as === 'api' ? conversation.api : conversation.rows
      },
    },
    state: {
      get: async (ref: { plugin: string; key: string }) => ({ value: kept.get(`${ref.plugin}.${ref.key}`), version: 0 }),
      set: async (ref: { plugin: string; key: string }, value: unknown) => {
        const key = `${ref.plugin}.${ref.key}`
        const n = (sets.get(key) ?? 0) + 1
        sets.set(key, n)
        calls.push({ op: 'state.set', args: { key, value } })
        if (options.refuseSet?.(key, n) === true) throw new Error(`the host refused ${key}`)
        kept.set(key, JSON.parse(JSON.stringify(value)))
        return { isSet: true }
      },
    },
    fs: {
      write: async (path: string, text: string) => {
        calls.push({ op: 'fs.write', args: { path, bytes: new TextEncoder().encode(text).length } })
        files.set(path, text)
      },
      read: async (path: string) => {
        const text = files.get(path)
        if (text === undefined) throw new Error(`ENOENT: ${path}`)
        return text
      },
      exists: async (path: string) => files.has(path) || (options.record === true && path === `${HOME}/sheet/${session}/state.json`),
      list: async (path: string) => {
        calls.push({ op: 'fs.list', args: path })
        return [...files.keys()].filter((file) => file.startsWith(`${path}/`) && !file.slice(path.length + 1).includes('/')).map((file) => ({ name: file.slice(path.length + 1), kind: 'file', size: 1, mtimeMs: 0, isLink: false }))
      },
      stat: async (path: string, opts?: { resolve?: boolean }) => {
        calls.push({ op: 'fs.stat', args: path })
        const text = files.get(path)
        // The sheet's own files are there when written; a reference's file stands (Read refuses a missing one).
        if (text === undefined && path.startsWith(`${HOME}/`)) throw new Error(`ENOENT: ${path}`)
        return { kind: 'file', size: text === undefined ? 5 : new TextEncoder().encode(text).length, mtimeMs: 1763900000000, isLink: false, ...(opts?.resolve === true && { realPath: `/real${path}` }) }
      },
    },
    process: {
      hookEnv: async () => (options.enginePid === null ? {} : { CLAUDE_PID: options.enginePid ?? ENGINE_PID }),
      run: async (argv: readonly string[], init?: { stdin?: string }) => {
        calls.push({ op: 'process.run', args: argv })
        if (argv[0] !== COMMAND && options.exec !== undefined) return { stderr: '', isStdoutTruncated: false, isStderrTruncated: false, ...(await options.exec(argv)) }
        if (argv[0] !== COMMAND) throw new Error(`no such command ${argv[0]}`)
        const [verb, op] = [argv[1], argv[2]]
        if (verb === 'sheet' && op === 'probe') {
          return { exitCode: 0, stdout: JSON.stringify(options.probe ?? { ...ALIVE, surface: null, surfaces: 0 }), stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
        }
        if (verb === 'sheet' && op === 'log') {
          projections += 1
          const out = options.log === undefined ? { exitCode: 0 } : await options.log(projections)
          return { stdout: '', stderr: '', ...out, isStdoutTruncated: false, isStderrTruncated: false }
        }
        if (verb === 'sheet' && op === 'witness') {
          witnesses += 1
          const out = options.witness === undefined ? { exitCode: 0, stdout: `${W1}\n` } : options.witness(witnesses)
          return { stdout: '', stderr: '', ...out, isStdoutTruncated: false, isStderrTruncated: false }
        }
        if (verb === 'sheet' && op === 'remove') {
          return { exitCode: options.remove ?? 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
        }
        if (verb === 'sheet' && op === 'step') {
          // The session a step is ordered for, beside its event.
          const event = { ...(JSON.parse(init?.stdin ?? '{}') as StepEvent), session: argv[4] }
          steps.push(event)
          const stdout = await (options.step ?? defaultStep)(event, steps.length)
          return { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
        }
        throw new Error(`unscripted: ${argv.join(' ')}`)
      },
    },
    tool: {
      list: async () => [{ name: 'AskUserQuestion', description: 'The built-in.', mcp: false }],
      register: async (spec: unknown) => (calls.push({ op: 'tool.register', args: spec }), { tool: SHEET_TOOL }),
      check: async ({ input }: { input: { file_path: string } }) => {
        calls.push({ op: 'tool.check', args: input })
        return options.checks?.[input.file_path] ?? { decision: 'allow' }
      },
      call: async (args: { tool: string; file_path: string }) => {
        calls.push({ op: 'tool.call', args })
        return (
          options.reads?.[args.file_path] ?? {
            result: { type: 'text', file: { filePath: args.file_path, content: `content of ${args.file_path}\n`, numLines: 1, startLine: 1, totalLines: 1 } },
            text: '1\tcontent',
          }
        )
      },
    },
    agent: { list: async () => (calls.push({ op: 'agent.list', args: undefined }), options.agents ?? []) },
    ui: {
      log: (text: string) => calls.push({ op: 'ui.log', args: text }),
      toast: (text: string) => calls.push({ op: 'ui.toast', args: text }),
      notify: async (text: string) => (calls.push({ op: 'ui.notify', args: text }), { isSent: true }),
      invalidate: (event: string) => calls.push({ op: 'ui.invalidate', args: event }),
      resolve: () => ({ Box: 'Box', Text: 'Text', Button: 'Button' }),
    },
    clock: {
      now: async () => options.now ?? Date.parse('2026-11-24T10:00:30.000Z'),
      every: (_ms: number, fn: () => void) => (timers.push(fn), { cancel: () => {} }),
      after: (_ms: number, fn: () => void) => {
        afters.push(fn)
        return {
          cancel: () => {
            const at = afters.indexOf(fn)
            if (at >= 0) afters.splice(at, 1)
          },
        }
      },
    },
    prompt: {
      submit: async ({ text }: { text: string }) => {
        calls.push({ op: 'prompt.submit', args: text })
        submits.push(text)
        return options.submit !== undefined ? options.submit(text) : { text }
      },
    },
  }
  resetAsk()
  resetSheet()
  registerSheetBand(on)
  registerAskBand(on)
  registerSheet(on)
  registerAsk(on)

  const matches = (matcher: Matcher, e: Record<string, unknown>) =>
    Object.entries(matcher ?? {}).every(([k, v]) => (v instanceof RegExp ? v.test(String(e[k])) : e[k] === v))
  /** A dispatch; `deadline`, when it resolves first, is the engine giving up on a hook (its budget): the hook's failure handler answers. */
  const dispatch = (event: string, e: Record<string, unknown>, origin: Origin, bottom: (e: Record<string, unknown>) => unknown, deadline?: Promise<void>, signal = new AbortController().signal) => {
    const chain = hooks.filter((h) => h.event === event && matches(h.matcher, e))
    const at = async (i: number, input: Record<string, unknown>): Promise<unknown> => {
      const hook = chain[i]
      if (hook === undefined) return bottom(input)
      let called = false
      const next = Object.assign(async (inner: Record<string, unknown>) => ((called = true), at(i + 1, inner)), { origin, signal })
      try {
        const ran = Promise.resolve(hook.handler($, input, next))
        return await (deadline === undefined ? ran : Promise.race([ran, deadline.then(() => Promise.reject(new Error('the hook ran out of time')))]))
      } catch (error) {
        if (hook.onFailure === undefined) throw error
        return hook.onFailure($, input, Object.assign(next, { called, error: { kind: 'threw', message: String(error) } }))
      }
    }
    return at(0, e)
  }
  // Microtask turns, so work a hook only triggered runs to its end.
  const settle = async () => {
    for (let i = 0; i < 200; i++) await Promise.resolve()
  }

  const start = (isInteractive = options.isInteractive ?? true) =>
    dispatch('session.start', { cwd: '/work', surface: isInteractive ? 'terminal' : null, isInteractive }, MODEL, async () => ({ cwd: '/work' }))
  const classicStart = (source: string, id = session) => {
    session = id
    return dispatch('classic.SessionStart', { hook_event_name: 'SessionStart', source, session_id: id, transcript_path: `/t/${id}.jsonl`, cwd: '/work' }, MODEL, async () => ({}))
  }
  const sessionEnd = (reason: string) => dispatch('session.end', { reason, sessionId: session, resume: {} }, MODEL, async () => ({ sessionId: session }))
  /** A call of `tool` from the model (or a subagent); what reached beneath, if anything. */
  const call = async (tool: string, args: Record<string, unknown>, agentId?: string, origin = MODEL, deadline?: Promise<void>, signal?: AbortSignal, beneath?: unknown) => {
    const ran: Record<string, unknown>[] = []
    const e = { tool, tool_use_id: `toolu_${steps.length}_${calls.length}`, ...args, ...(agentId !== undefined && { agentId }) }
    const result = await dispatch('tool.call', e, origin, async (inner) => (ran.push(inner), beneath ?? { ref: 9, result: 'ran', text: 'ran' }), deadline, signal)
    return { result: result as { result?: unknown; deny?: string; context?: string[] }, ran, id: e.tool_use_id }
  }
  const ask = (args: Record<string, unknown>, agentId?: string) => call(SHEET_TOOL, args, agentId)
  const describe = (tool: string, description: string) =>
    dispatch('tool.describe', { tool, description, isDeferred: true, provider: MODEL }, MODEL, async (e) => ({ description: e.description, isDeferred: e.isDeferred }))
  const render = (component: string, props: Record<string, unknown>) => dispatch('ui.render', { component, props, surface: 'terminal' }, MODEL, async () => 'beneath')
  /** Runs the `$.clock.after` callbacks queued so far (the hop out of a dispatch), then lets their work run. */
  const hop = async () => {
    for (let i = 0; i < 20 && afters.length > 0; i++) {
      afters.splice(0).forEach((fn) => fn())
      await settle()
    }
  }
  const tick = async () => {
    timers.forEach((fn) => fn())
    await settle()
    await hop()
  }
  /** A main turn (or a subagent's, with `agentId`) starts and completes. */
  const turnStart = (turnId: string, agentId?: string) => dispatch('turn.start', { text: '', turnId, ...(agentId !== undefined && { agentId }) }, MODEL, async (e) => ({ turnId: e.turnId }))
  const turnComplete = (turnId: string, reason = 'answer', agentId?: string) =>
    dispatch('turn.complete', { turnId, reason, durationMs: 1, isAborted: reason === 'aborted', ...(agentId !== undefined && { agentId }) }, MODEL, async () => ({ text: '' }))
  /** A row appended: what reaches the bottom is stored as it arrived. */
  const append = (e: { door: string; origin: unknown; agentId?: string; text: string; type?: string }) =>
    dispatch(
      'session.append',
      { door: e.door, origin: e.origin, uuid: `u${calls.length}`, message: { type: e.type ?? 'user', role: 'user', content: [{ type: 'text', text: e.text }] }, ...(e.agentId !== undefined && { agentId: e.agentId }) },
      MODEL,
      async (inner) => ({ message: inner.message, uuid: inner.uuid }),
    )
  /** A prompt enters (`prompt.submit`): what reached the bottom answers, unless `bottom` says otherwise. */
  const prompt = (text: string, over: Record<string, unknown> = {}, bottom?: (e: Record<string, unknown>) => unknown) =>
    dispatch('prompt.submit', { text, wait: false, origin: { kind: 'composer' }, ...over }, MODEL, bottom ?? (async (e) => ({ text: e.text, context: e.context, origin: e.origin })))
  const registered = () => calls.filter((c) => c.op === 'tool.register').map((c) => c.args as { name: string; description: string; inputSchema: unknown })
  const runs = () => calls.filter((c) => c.op === 'process.run').map((c) => (c.args as string[]).slice(1).join(' '))
  const writes = () => calls.filter((c) => c.op === 'fs.write').map((c) => c.args as { path: string; bytes: number })
  const logs = () => calls.filter((c) => c.op === 'ui.log').map((c) => c.args as string)
  const staged = (path: string) => JSON.parse(files.get(path) ?? 'null') as Record<string, unknown>

  /** A session under the sheet whose start has answered. */
  const ready = async (source = 'startup') => {
    await start()
    await classicStart(source)
    await settle()
  }
  return { submits, sends, afters, hop, turnStart, turnComplete, append, prompt, calls, steps, files, kept, timers, start, classicStart, sessionEnd, call, ask, describe, render, tick, settle, registered, runs, writes, logs, staged, ready, engine: $ as unknown as EngineInterface, dispatch: (event: string, e: Record<string, unknown>) => dispatch(event, e, MODEL, async () => ({})), converse: (held: typeof conversation) => (conversation = held) }
}

/** The command's step for a test that scripts none: a start, a drain, a call that adds one, all at seq n. */
export const defaultStep: StepScript = (event, n) => (event.event === 'call' ? ok(n, { result: 'Added q1.' }, { nextId: 2 }) : ok(n))

export const SHEET_ON = { SMINOS_QUESTION_SHEET: '1' }
export const sheetOn = (over: Parameters<typeof harness>[0] = {}) => harness({ env: SHEET_ON, probe: ALIVE, ...over, ...(over.env !== undefined && { env: { ...SHEET_ON, ...over.env } }) })

/** A step script whose events of the kinds named wait until released, each by its own release. */
export function gated(kinds: readonly string[], otherwise: StepScript = defaultStep) {
  const waiting: { event: StepEvent; release: (stdout?: string | Error) => void }[] = []
  const script: StepScript = (event, n) =>
    kinds.includes(event.event)
      ? new Promise<string>((resolve, reject) =>
          waiting.push({ event, release: (out) => (out instanceof Error ? reject(out) : resolve(out ?? (otherwise(event, n) as string))) }),
        )
      : otherwise(event, n)
  return { script, waiting }
}

/** The texts a drawn tree shows, in order (the test runtime's elements are `{ type, props, children }`). */
export function textsOf(tree: unknown): string[] {
  if (typeof tree === 'string') return [tree]
  if (Array.isArray(tree)) return tree.flatMap(textsOf)
  if (typeof tree === 'object' && tree !== null && 'children' in tree) return textsOf((tree as { children: unknown }).children)
  return []
}

/** The lines a drawn tree's Text elements show, each joined. */
export function linesOf(tree: unknown): string[] {
  if (Array.isArray(tree)) return tree.flatMap(linesOf)
  if (typeof tree !== 'object' || tree === null) return []
  const element = tree as { type?: unknown; children?: unknown }
  return element.type === 'Text' ? [textsOf(element.children).join('')] : linesOf(element.children)
}
