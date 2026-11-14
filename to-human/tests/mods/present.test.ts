import type { EngineInterface, On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import { MESSAGE_TOOL, TO_HUMAN_STYLE, endsOnFinal, note } from '../../hooks/mods/message'
import {
  BUSY,
  DESCRIPTION,
  EMPTY_REFUSAL,
  FAILED,
  FINISHED,
  FORK_DESCRIPTION,
  GUARD_REFUSAL,
  INPUT_SCHEMA,
  LOCAL_ONLY,
  LOOKED_MEANWHILE,
  NOT_HEARD,
  PLAN_REFUSAL,
  PRESENT_TOOL,
  REMOVED,
  STANDING_PROMPT,
  STARTED,
  SUBAGENT_REFUSAL,
  briefLine,
  forgetPresent,
  registerPresent,
  rowOf,
} from '../../hooks/mods/present'
import type { OpenPanel } from '../../hooks/mods/present'

// The kit runs tests with the timer the hooks' declarations leave out.
declare const setTimeout: (callback: (value?: unknown) => void, ms: number) => unknown

tier('user')

const SESSION = 'b4d10f41-4268-45ce-ad05-309f05c3ee48'
const ROOT = '/cfg/to-human/panels/b4d10f41'
const DRAFT = `${ROOT}/draft.html`
const ADDRESS = 'http://127.0.0.1:4791/b4d10f41/'
const FORK = 'afork00000000001'
const SAID = 'The panel holds the two options.\nFirst write.'

const OPEN: OpenPanel = {
  address: ADDRESS,
  reach: 'tailnet',
  dir: ROOT,
  draft: DRAFT,
  guide: '/plugin/panel/base/GUIDE.md',
  update: 3,
  isNew: false,
  locale: 'en',
  seen: 'current',
  checked: ['u2-1'],
}

const PUBLISHED = { published: true, address: ADDRESS, reach: 'tailnet', written: 1794620000000, removed: [] as string[], lookedMeanwhile: false }
/** When a run starts, by the harness's clock: before PUBLISHED.written. */
const NOW = 1794619990000

type Answer = { exitCode: number; stdout: string; stderr: string }
const ok = (value: unknown): Answer => ({ exitCode: 0, stdout: `${JSON.stringify(value)}\n`, stderr: '' })
const failing = (line: string): Answer => ({ exitCode: 1, stdout: '', stderr: `${line}\n` })
/** Lets every unawaited continuation run. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

type Handler = (...args: unknown[]) => unknown
type Registration = { event: string; matcher: Record<string, unknown>; handler: Handler; caught?: Handler }
type Event = Record<string, unknown>
const PLUGIN = { plugin: 'to-human', tier: 'user' }
const ENGINE = { plugin: 'engine', tier: 'core' }

/** Every harness made below, with the hook failures it saw: the last test holds them to none unexpected. */
const harnesses: { failures: string[]; failsClosed: boolean }[] = []

/**
 * The present module's hooks run as the engine runs one plugin's: each
 * matching hook outermost first (the first registered), a failed hook's
 * `.catch` asked in its place, down to `core`; over a `$` of plain records.
 * The kit's own engine strips `agentId` from any spawn a hook answers ("set
 * by core"), so the flows that need a fork are run here.
 *
 * `server` answers each command line, `spawn` the engine's spawn (FORK by
 * default), `agents` the agent list (a throw is a list that cannot be read),
 * `links` where a path lands (a path not listed lands on itself; null leads
 * nowhere), `unreadable` the `$.state` keys whose read fails, `unwritable`
 * those whose write fails, `stalled` those whose write waits until
 * `release()`.
 *
 * A continuation is replay-safe, as the engine's is: a `.catch` that calls
 * `next` after its hook had called it gets the settled result again, and
 * nothing beneath runs twice. `failures` lists each hook's own throw (not one
 * that came up from beneath), `logs` what the module logged. A hook may fail
 * only where `failsClosed` says the test means it to (the guard refusing a
 * call it cannot place); the file's last test checks every harness.
 */
function harness({
  env = {},
  server = {},
  spawn,
  agents = () => [{ id: FORK, description: FORK_DESCRIPTION, type: 'fork', status: 'running', spawnedBy: 'to-human' }],
  links = {},
  unreadable = new Set<string>(),
  unwritable = new Set<string>(),
  stalled = new Set<string>(),
  failsClosed = false,
}: {
  env?: Record<string, string>
  server?: { open?: () => Answer | Promise<Answer>; publish?: () => Answer | Promise<Answer> }
  spawn?: () => Record<string, unknown> | undefined
  agents?: () => Record<string, unknown>[] | Promise<Record<string, unknown>[]>
  links?: Record<string, string | null>
  unreadable?: Set<string>
  unwritable?: Set<string>
  stalled?: Set<string>
  failsClosed?: boolean
} = {}) {
  forgetPresent()
  const hooks: Registration[] = []
  const on = ((event: string, ...rest: unknown[]) => {
    const r: Registration = { event, matcher: rest.length > 1 ? (rest[0] as Event) : {}, handler: rest[rest.length - 1] as Handler }
    hooks.push(r)
    return { catch: (h: Handler) => void (r.caught = h) }
  }) as unknown as On
  registerPresent(on)

  const state = new Map<string, unknown>()
  const commands: (readonly string[])[] = []
  const spawned: Event[] = []
  const notified: string[] = []
  const sleeps: number[] = []
  const failures: string[] = []
  const logs: string[] = []
  harnesses.push({ failures, failsClosed })
  const waiting: (() => void)[] = []
  /** Lets every stalled write go, and stalls none after. */
  const release = async () => {
    stalled.clear()
    waiting.splice(0).forEach((go) => go())
    await settle()
  }
  const matches = (r: Registration, event: string, e: Event) =>
    r.event === event && Object.entries(r.matcher).every(([k, v]) => (v instanceof RegExp ? v.test(String(e[k])) : e[k] === v))

  const run = async (event: string, e: Event, core: (e: Event) => unknown, origin = ENGINE): Promise<unknown> => {
    const chain = hooks.filter((r) => matches(r, event, e))
    const at = async (i: number, input: Event): Promise<unknown> => {
      const r = chain[i]
      if (r === undefined) return core(input)
      let called = false
      let settled: Promise<unknown> | undefined
      let beneath: unknown
      const next = Object.assign(
        (inner: Event) => {
          called = true
          if (settled === undefined) {
            settled = at(i + 1, inner)
            settled.catch((error: unknown) => (beneath = error))
          }
          return settled
        },
        { origin },
      )
      try {
        return await r.handler($, input, next)
      } catch (error) {
        if (error !== beneath) failures.push(`${event}#${hooks.indexOf(r)}: ${String(error)}`)
        if (r.caught === undefined) return settled ?? at(i + 1, input)
        return r.caught($, input, Object.assign(next, { called, error: { kind: 'throw', message: String(error) } }))
      }
    }
    return at(0, e)
  }

  const $ = {
    plugin: { name: 'to-human', root: '/plugin' },
    state: {
      get: async (ref: { key: string }) => {
        if (unreadable.has(ref.key)) throw new Error(`state.get ${ref.key}: the store is not answering`)
        return { value: state.get(ref.key), version: 0 }
      },
      set: async (ref: { key: string }, value: unknown) => {
        if (stalled.has(ref.key)) await new Promise<void>((resolve) => waiting.push(resolve))
        if (unwritable.has(ref.key)) throw new Error(`state.set ${ref.key}: the store is not answering`)
        state.set(ref.key, value)
        return { isSet: true, version: 1 }
      },
    },
    process: {
      run: async (argv: readonly string[]) => {
        commands.push(argv)
        const verb = argv[2]
        const answer = verb === 'open-panel' ? await (server.open ?? (() => ok(OPEN)))() : verb === 'publish' ? await (server.publish ?? (() => ok(PUBLISHED)))() : ok({})
        return { ...answer, isStdoutTruncated: false, isStderrTruncated: false }
      },
    },
    agent: {
      // Every hook but the calling one (the handler's, which is no agent.spawn hook), under this plugin's origin.
      spawn: (input: Event) =>
        run('agent.spawn', { ...input, fork: true, background: true, permissionMode: 'default', parentModel: 'claude-haiku' }, (e) => {
          spawned.push(e)
          return spawn?.() ?? { model: 'claude-haiku', agentId: FORK }
        }, PLUGIN),
      list: async () => agents(),
    },
    session: { id: async () => SESSION },
    env: { get: async (name: string) => env[name] },
    fs: {
      stat: async (path: string) => {
        const real = path in links ? links[path] : path
        if (real === null) throw new Error(`ENOENT: ${path}`)
        return { kind: 'file', size: 1, mtimeMs: 0, isLink: path !== real, realPath: real }
      },
    },
    ui: {
      notify: async (text: string) => (notified.push(text), { isSent: true, channel: 'terminal_bell' }),
      log: (text: string) => void logs.push(text),
    },
    clock: { sleep: async (ms: number) => void sleeps.push(ms), now: async () => NOW },
    tool: { register: async () => ({ tool: PRESENT_TOOL }) },
  } as unknown as EngineInterface

  const present = (brief: unknown, { agentId, id = 'toolu_p1' }: { agentId?: string; id?: string } = {}) =>
    run('tool.call', { tool: PRESENT_TOOL, tool_use_id: id, brief, ...(agentId !== undefined && { agentId }) }, () => {
      throw new Error('no tool serves it')
    }) as Promise<Record<string, unknown>>
  /** A call of another tool, raised by `origin` (the engine's: the model's), answered `ran` beneath (or by `core`). */
  const call = (tool: string, input: Event = {}, agentId?: string, core: (e: Event) => unknown = () => ({ result: 'ran' }), origin = ENGINE) =>
    run('tool.call', { tool, tool_use_id: `toolu_${tool}`, ...input, ...(agentId !== undefined && { agentId }) }, core, origin) as Promise<Record<string, unknown>>
  const check = (
    tool: string,
    input: Event = {},
    { agentId = FORK, isReadOnly = false, core = 'ask', origin = ENGINE }: { agentId?: string; isReadOnly?: boolean; core?: string; origin?: typeof ENGINE } = {},
  ) => run('tool.check', { tool, input, tool_use_id: `toolu_${tool}`, ...(agentId !== '' && { agentId }), ...(isReadOnly && { isReadOnly: true }) }, () => ({ decision: core }), origin)
  /** The fork's end, as every hook hears an agent's turn.complete; then its close settles. */
  const ended = async (fields: Event = {}) => {
    await run('turn.complete', { turnId: 'tf', answer: SAID, durationMs: 9, isAborted: false, reason: 'answer', agentId: FORK, ...fields }, () => ({ text: '' }))
    await settle()
  }
  /** A prompt through the hooks, answered (or dropped) beneath; what reached beneath. */
  const prompt = async (text: string, drop = false) => {
    let reached: Event | undefined
    const result = await run('prompt.submit', { text, origin: { kind: 'composer' } }, (e) => ((reached = e), drop ? { drop: 'screened' } : { text: e.text }))
    return { result, context: reached?.context }
  }
  /** A classic event as the engine raises it. */
  const classic = (e: Event) => run(`classic.${String(e.hook_event_name)}`, e, () => ({}))
  /** The engine's record of a switch of mode, naming the loop it happened in (none: the main loop's). */
  const modeChanged = (to: string, agentId?: string) =>
    run('telemetry.log', { to: 'collector', event: 'permission_mode_changed', attributes: { to_mode: to, ...(agentId !== undefined && { agent_id: agentId }) } }, () => ({ value: undefined }))
  const start = async (isInteractive = true) => {
    await run('session.start', { cwd: '/w', surface: null, isInteractive }, () => ({ cwd: '/w' }))
    await settle()
  }
  return { present, call, check, ended, prompt, start, classic, modeChanged, release, state, commands, spawned, notified, sleeps, failures, logs }
}

describe('the present tool: its contract', () => {
  test("the name, the description and the one input field are the spec's", () => {
    expect(PRESENT_TOOL).toBe('mcp__to-human__present')
    expect(DESCRIPTION).toBe("Put something on this session's panel for the human; a fork of you writes it in the background.")
    expect(INPUT_SCHEMA).toEqual({
      type: 'object',
      properties: { brief: { type: 'string', description: 'What to put on the panel or change on it. The fork has the conversation up to this call.' } },
      required: ['brief'],
    })
  })

  test("BUSY and the guard's refusal are worded as Interfaces has them", () => {
    expect(BUSY(ADDRESS)).toBe(
      `The panel is being written now: ${ADDRESS} Go on with your work: you are told at your next step once it is written, and can call present again then with what to change.`,
    )
    expect(GUARD_REFUSAL).toBe(
      "Refused: this fork writes the panel and nothing else; that step is the session's, and the session takes it. Go on editing the draft, and end with your two-line reply once it holds the panel.",
    )
  })

  test('the standing prompt is assembled from an OpenPanel and the brief', () => {
    const prompt = STANDING_PROMPT(OPEN, 'Lay out options A and B.')
    expect(prompt.startsWith('You are a fork of this session, started by its `present` call')).toBe(true)
    expect(prompt).toContain('You are not the session: do not continue its task, answer its human, or call `present`.')
    expect(prompt).toContain(`Edit ${DRAFT}: it is the panel as it stands, and it is published when you end. This is update 3. Write it in English.`)
    expect(prompt).toContain(`on the base the page links: ${OPEN.guide} lists its blocks and the markup of a note.`)
    expect(prompt).toContain('Keep it to about three screens: 600 to 900 words of running text')
    expect(prompt).toContain('The human has looked at the panel since its last update: they have seen what it holds.\nWhere an edit changes')
    expect(prompt).toContain(
      'Where an edit changes what they have seen, write one note for that change, saying what changed and why, at the first place it shows, and mark each other place it changed with the same id; ids u3-1, u3-2, and so on, one per change. A note still on the page whose statement you change again is replaced by one note carrying both steps.',
    )
    expect(prompt).toContain('replaced by one note carrying both steps. Delete these notes, which they checked off, with every mark of their ids: u2-1.')
    expect(prompt).toContain(`You can read anything and write only ${DRAFT}. Reply with two lines: what the panel now holds, and what changed.`)
    expect(prompt.endsWith('\n\nBrief: Lay out options A and B.')).toBe(true)
  })

  test('a new Korean panel nobody looked at: the starter, Korean, its measure in characters, no notes owed', () => {
    const prompt = STANDING_PROMPT({ ...OPEN, isNew: true, update: 1, locale: 'ko', seen: 'never', checked: [] }, 'x')
    expect(prompt).toContain('it is the panel as it stands, a starter with nothing on it yet, and it is published when you end. This is update 1. Write it in Korean.')
    expect(prompt).toContain('1,800 to 2,700 characters of running text')
    expect(prompt).toContain('The human has not looked at the panel: it owes them no notes.')
    expect(prompt).not.toContain('Delete these notes')
  })

  test('a page whose last update nobody saw', () => {
    expect(STANDING_PROMPT({ ...OPEN, seen: 'stale', checked: [] }, 'x')).toContain(
      'The human has not looked at the panel since its last update: what that update wrote, they have not seen.',
    )
  })

  test("a call's row reads the brief's first line, whole or streaming", () => {
    expect(briefLine({ brief: '\n  Two options for the cache.\nDetails follow.' })).toBe('Two options for the cache.')
    expect(briefLine('{"brief":"Streaming in')).toBe('Streaming in')
    expect(briefLine({})).toBe('')
  })

  test("a call's row state: by the call's id, else the address its result carries", () => {
    const presented = {
      a: { state: 'writing' as const, address: ADDRESS },
      b: { state: 'written' as const, address: ADDRESS },
      c: { state: 'failed' as const, address: ADDRESS, why: 'the fork changed nothing on it' },
    }
    expect(rowOf(presented, 'a', undefined)).toEqual({ state: 'writing', address: ADDRESS })
    expect(rowOf(presented, 'b', STARTED(ADDRESS))).toEqual({ state: 'written', address: ADDRESS })
    expect(rowOf(presented, 'c', undefined)).toEqual({ state: 'failed', address: ADDRESS, why: 'the fork changed nothing on it' })
    expect(rowOf(undefined, 'd', STARTED(ADDRESS) + LOCAL_ONLY)).toEqual({ state: 'unknown', address: ADDRESS })
    const tailnet = 'https://s.tail112c3f.ts.net:4777/b4d10f41/'
    expect(rowOf(undefined, 'd', [{ type: 'text', text: STARTED(tailnet) }])).toEqual({ state: 'unknown', address: tailnet })
    expect(rowOf(undefined, 'd', undefined)).toBeUndefined()
  })
})

/**
 * The kit's engine beneath the whole plugin, for where the tool is offered:
 * a session under the to-human style, the panel server's command line
 * recorded and answered `{}`.
 */
function kit(on: On, env: Record<string, string> = {}) {
  mock.env(on, env)
  mock.store(on)
  const clock = mock.clock(on)
  const registered: string[] = []
  const commands: (readonly string[])[] = []
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: SESSION }))
  on('tool.register', (_, e) => {
    const tool = `mcp__to-human__${e.name}`
    registered.push(tool)
    return { value: { tool } }
  })
  on('tool.describe', (_, e) => ({ description: e.description, isDeferred: true }))
  on('config.list', () => ({
    value: [{ key: 'outputStyle', label: 'Output style', kind: 'choice', value: TO_HUMAN_STYLE, options: ['default'], provider: { plugin: 'engine', tier: 'core' }, isLocked: false }],
  }))
  on('process.run', async (_, e) => (commands.push(e.argv), { value: { exitCode: 0, stdout: '{}\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('ui.log', () => ({ value: undefined }))
  return { clock, registered, commands }
}
const start = ($: Engine, isInteractive = true) => $.session.start({ cwd: '/w', surface: null, isInteractive })

describe('the present tool: where it is offered', () => {
  test('an interactive session under the style gets it beside the message tool, always loaded', async ($, on) => {
    const { registered } = kit(on)
    await start($)
    expect(registered).toEqual([MESSAGE_TOOL, PRESENT_TOOL])
    expect(await $.tool.describe({ tool: PRESENT_TOOL, description: DESCRIPTION, isDeferred: true, provider: { plugin: 'to-human', tier: 'user' } })).toEqual({
      description: DESCRIPTION,
      isDeferred: false,
    })
  })

  for (const env of [{ MAWS_NATIVE_TO_HUMAN: '8' }, { MAWS_NATIVE_TO_HUMAN: 'native' }, { SMNS_INTERNAL: '1' }] as Record<string, string>[]) {
    test(`not in a session nobody reads in a browser beside it: ${JSON.stringify(env)}`, async ($, on) => {
      const { registered } = kit(on, env)
      await start($)
      expect(registered).toEqual([MESSAGE_TOOL])
    })
  }

  test('not in a headless session, even one MAWS reads', async ($, on) => {
    const { registered } = kit(on, { MAWS_NATIVE_TO_HUMAN: '8' })
    await start($, false)
    expect(registered).toEqual([MESSAGE_TOOL])
  })

  test('not under another output style, where the message tool is not either', async ($, on) => {
    mock.env(on, {})
    on('session.start', (_, e) => ({ cwd: e.cwd }))
    const registered: string[] = []
    on('tool.register', (_, e) => (registered.push(e.name), { value: { tool: `mcp__to-human__${e.name}` } }))
    on('config.list', () => ({ value: [{ key: 'outputStyle', label: 'Output style', kind: 'choice', value: 'default', options: ['default'], provider: { plugin: 'engine', tier: 'core' }, isLocked: false }] }))
    on('process.run', async () => ({ value: { exitCode: 0, stdout: '{}\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
    await start($)
    expect(registered).toEqual([])
  })

  test('an interactive start makes sure the panel server answers, by its command line, unawaited', async ($, on) => {
    const { commands, clock } = kit(on)
    await start($)
    await clock.settle()
    const ensures = commands.filter((argv) => argv[2] === 'ensure')
    expect(ensures).toHaveLength(1)
    expect(ensures[0]![0]).toBe('python3')
    expect(ensures[0]![1]!.endsWith('/to-human/panel/server.py')).toBe(true)
  })

  test('a headless start does not', async ($, on) => {
    const { commands, clock } = kit(on)
    await start($, false)
    await clock.settle()
    expect(commands.some((argv) => argv[2] === 'ensure')).toBe(false)
  })

  test("a subagent's call and an empty brief are refused, before anything runs", async ($, on) => {
    const { commands, clock } = kit(on)
    await start($)
    await clock.settle()
    const before = commands.length
    expect(await $.tool.call({ tool: PRESENT_TOOL, brief: 'x', agentId: 'agent-1' } as never)).toEqual({ deny: SUBAGENT_REFUSAL })
    expect(await $.tool.call({ tool: PRESENT_TOOL, brief: '  \n' } as never)).toEqual({ deny: EMPTY_REFUSAL })
    expect(await $.tool.call({ tool: PRESENT_TOOL } as never)).toEqual({ deny: EMPTY_REFUSAL })
    expect(commands.length).toBe(before)
  })
})

describe('the present tool: the call', () => {
  test('a main-conversation call opens the panel, spawns the fork with the standing prompt, and returns STARTED', async () => {
    const h = harness({ env: { PANEL_LOCALE: 'korean' } })
    expect(await h.present('Lay out options A and B.')).toEqual({ result: STARTED(ADDRESS) })
    expect(h.commands.map((argv) => argv.slice(1))).toEqual([['/plugin/panel/server.py', 'open-panel', '--session', SESSION, '--locale', 'korean']])
    expect(h.spawned).toHaveLength(1)
    expect(h.spawned[0]).toMatchObject({ subagentType: 'fork', description: FORK_DESCRIPTION, prompt: STANDING_PROMPT(OPEN, 'Lay out options A and B.') })
    expect(h.state.get('present')).toEqual({
      agentId: FORK,
      toolUseId: 'toolu_p1',
      session: SESSION,
      dir: ROOT,
      draft: DRAFT,
      address: ADDRESS,
      update: 3,
      startedAt: NOW,
      phase: 'writing',
    })
    expect(h.state.get('presentForks')).toEqual([FORK])
    expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'writing', address: ADDRESS } })
  })

  test('with PANEL_LOCALE unset the server reads no --locale', async () => {
    const h = harness()
    await h.present('x')
    expect(h.commands[0]!.slice(2)).toEqual(['open-panel', '--session', SESSION])
  })

  test('a panel that opens only on this machine says so', async () => {
    const h = harness({ server: { open: () => ok({ ...OPEN, reach: 'local' }) } })
    expect(await h.present('x')).toEqual({ result: STARTED(ADDRESS) + LOCAL_ONLY })
  })

  test('a call while the fork writes is BUSY, and nothing more is opened or spawned', async () => {
    const h = harness()
    await h.present('first')
    expect(await h.present('second', { id: 'toolu_p2' })).toEqual({ deny: BUSY(ADDRESS) })
    expect(h.commands.filter((argv) => argv[2] === 'open-panel')).toHaveLength(1)
    expect(h.spawned).toHaveLength(1)
  })

  test('a second call arriving while open-panel runs is BUSY: the reservation is taken before the first await', async () => {
    let release = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    const h = harness({ server: { open: async () => (await gate, ok(OPEN)) } })
    const first = h.present('first')
    const second = h.present('second', { id: 'toolu_p2' })
    await settle()
    release()
    expect(await first).toEqual({ result: STARTED(ADDRESS) })
    expect(await second).toEqual({ deny: BUSY(ADDRESS) })
    expect(h.spawned).toHaveLength(1)
  })

  test('a fork that completes while a second call reads a lagging list: no hook fails, and the call starts the next run', async () => {
    let answer = () => {}
    let lagging = false
    const listed = [{ id: FORK, description: FORK_DESCRIPTION, type: 'fork', status: 'running', spawnedBy: 'to-human' }]
    const h = harness({ agents: () => (lagging ? new Promise((resolve) => (answer = () => resolve(listed))) : listed) })
    await h.present('first')
    lagging = true
    const second = h.present('second', { id: 'toolu_p2' })
    await settle()
    await h.ended()
    // The list, read before the end, still calls the fork running.
    lagging = false
    answer()
    expect(await second).toEqual({ result: STARTED(ADDRESS), context: [FINISHED(ADDRESS, SAID)] })
    expect(h.failures).toEqual([])
    expect(h.spawned).toHaveLength(2)
  })

  test("a call whose open-panel fails is refused with the command's line, and the next call is not BUSY", async () => {
    let fails = true
    const line = "server.py open-panel: port 4791 on this machine answers, but not as this configuration directory's panel server"
    const h = harness({ server: { open: () => (fails ? failing(line) : ok(OPEN)) } })
    expect(await h.present('x')).toEqual({ deny: line })
    expect(h.spawned).toEqual([])
    fails = false
    expect(await h.present('x', { id: 'toolu_p2' })).toEqual({ result: STARTED(ADDRESS) })
  })

  test('a spawn the engine denies is the refusal, and leaves no run open', async () => {
    let denies = true
    const h = harness({ spawn: () => (denies ? { deny: 'nothing is spawned past an interrupt until the session takes input' } : undefined) })
    expect(await h.present('x')).toEqual({ deny: "The panel's fork was not started: nothing is spawned past an interrupt until the session takes input" })
    expect(h.state.get('present') ?? null).toBeNull()
    denies = false
    expect(await h.present('x', { id: 'toolu_p2' })).toEqual({ result: STARTED(ADDRESS) })
  })

  test('in plan mode, as the prompt reported it, the call is refused before anything runs; a switch out opens it again', async () => {
    const h = harness()
    await h.classic({ hook_event_name: 'UserPromptSubmit', prompt: 'p', permission_mode: 'plan' })
    expect(await h.present('x')).toEqual({ deny: PLAN_REFUSAL })
    expect(h.commands).toEqual([])
    expect(h.spawned).toEqual([])
    await h.modeChanged('default')
    expect(await h.present('x', { id: 'toolu_p2' })).toEqual({ result: STARTED(ADDRESS) })
  })

  test("a switch into plan mode refuses the next call; a subagent's own mode is not the session's", async () => {
    const h = harness()
    await h.modeChanged('plan', 'agent-1')
    await h.classic({ hook_event_name: 'UserPromptSubmit', prompt: 'p', permission_mode: 'plan', agent_id: 'agent-1' })
    expect(await h.present('x')).toEqual({ result: STARTED(ADDRESS) })
    await h.ended()
    await h.modeChanged('plan')
    expect(await h.present('x', { id: 'toolu_p2' })).toEqual({ deny: PLAN_REFUSAL })
  })
})

describe("the present tool: the fork's end", () => {
  test('an answered end publishes; the row turns to the address, the human is notified, the session is told at its next call', async () => {
    const h = harness()
    await h.present('x')
    await h.ended()

    expect(h.commands.filter((argv) => argv[2] === 'publish').map((argv) => argv.slice(2))).toEqual([['publish', '--session', SESSION]])
    expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'written', address: ADDRESS } })
    expect(h.state.get('present')).toBeNull()
    expect(h.notified).toEqual([`The panel is written: ${ADDRESS}`])

    expect((await h.call('Bash', { command: 'true' })).context).toEqual([FINISHED(ADDRESS, SAID)])
    // Told once.
    expect((await h.call('Bash', { command: 'true' })).context).toBeUndefined()
  })

  test('the notice rides a result beside what it carries already, and never a refusal', async () => {
    const h = harness()
    await h.present('x')
    await h.ended()
    expect((await h.call('Bash', {}, undefined, () => ({ deny: 'no' }))).context).toBeUndefined()
    expect((await h.call('Bash', {}, undefined, () => ({ result: 'ran', context: ['theirs'] }))).context).toEqual(['theirs', FINISHED(ADDRESS, SAID)])
  })

  test('what publishing cut, a first look meanwhile, and a local reach follow the fork\'s words', async () => {
    const h = harness({ server: { publish: () => ok({ ...PUBLISHED, reach: 'local', removed: ['meta http-equiv', 'link'], lookedMeanwhile: true }) } })
    await h.present('x')
    await h.ended()
    expect((await h.call('Bash')).context).toEqual([`${FINISHED(ADDRESS, SAID)}\n${(REMOVED(['meta http-equiv', 'link']) + LOOKED_MEANWHILE + LOCAL_ONLY).trim()}`])
  })

  test('an end that changed nothing is not written; the session reads FAILED at its next prompt', async () => {
    const h = harness({ server: { publish: () => ok({ ...PUBLISHED, published: false }) } })
    await h.present('x')
    await h.ended()
    const why = 'the fork changed nothing on it'
    expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'failed', address: ADDRESS, why } })
    expect(h.notified).toEqual([`The panel was not written (${why})`])
    expect((await h.prompt('next')).context).toEqual([FAILED(ADDRESS, why)])
    expect((await h.prompt('after')).context).toBeUndefined()
  })

  for (const [reason, why] of [
    ['aborted', 'its fork was interrupted'],
    ['error', 'an API error ended its fork'],
    ['refusal', 'the model refused to write it'],
  ] as const) {
    test(`an end of reason ${reason} publishes nothing and is not written`, async () => {
      const h = harness()
      await h.present('x')
      await h.ended({ reason, isAborted: reason === 'aborted' })
      expect(h.commands.some((argv) => argv[2] === 'publish')).toBe(false)
      expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'failed', address: ADDRESS, why } })
      expect((await h.call('Read')).context).toEqual([FAILED(ADDRESS, why)])
    })
  }

  test("a publish that fails is not written, with the command's line as why", async () => {
    const h = harness({ server: { publish: () => failing('server.py publish: the panels directory cannot be written') } })
    await h.present('x')
    await h.ended()
    expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'failed', address: ADDRESS, why: 'server.py publish: the panels directory cannot be written' } })
  })

  test("another agent's end, and the main loop's, are no run's", async () => {
    const h = harness()
    await h.present('x')
    await h.ended({ agentId: 'another' })
    await h.ended({ agentId: undefined })
    expect(h.commands.some((argv) => argv[2] === 'publish')).toBe(false)
    expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'writing', address: ADDRESS } })
  })

  test('after the end the next call starts a new run', async () => {
    const h = harness()
    await h.present('x')
    await h.ended()
    // The new call's own result carries the last one's notice: it is the main loop's next tool result.
    expect(await h.present('again', { id: 'toolu_p2' })).toEqual({ result: STARTED(ADDRESS), context: [FINISHED(ADDRESS, SAID)] })
  })

  test('a prompt dropped beneath gives the notice back for the next one', async () => {
    const h = harness()
    await h.present('x')
    await h.ended()
    expect((await h.prompt('one', true)).context).toEqual([FINISHED(ADDRESS, SAID)])
    expect((await h.prompt('two')).context).toEqual([FINISHED(ADDRESS, SAID)])
    expect((await h.prompt('three')).context).toBeUndefined()
  })

  test("a plugin's own call carries no notice, since its result reaches no conversation; the next real result does", async () => {
    const h = harness()
    await h.present('x')
    await h.ended()
    expect((await h.call('TaskStop', { task_id: 'a1' }, undefined, undefined, { plugin: 'sminos', tier: 'user' })).context).toBeUndefined()
    expect((await h.call('Bash', {}, undefined, undefined, PLUGIN)).context).toBeUndefined()
    expect((await h.call('Bash')).context).toEqual([FINISHED(ADDRESS, SAID)])
  })

  test("a plugin's own call leaves the notice for the next prompt", async () => {
    const h = harness()
    await h.present('x')
    await h.ended()
    await h.call('TaskStop', { task_id: 'a1' }, undefined, undefined, { plugin: 'sminos', tier: 'user' })
    expect((await h.prompt('next')).context).toEqual([FINISHED(ADDRESS, SAID)])
  })

  test("a subagent's calls carry no notice: it is the session's", async () => {
    const h = harness()
    await h.present('x')
    await h.ended()
    expect((await h.call('Bash', {}, 'other')).context).toBeUndefined()
    expect((await h.call('Bash')).context).toHaveLength(1)
  })
})

describe('the present tool: a module that starts over mid-run', () => {
  /** A harness whose module forgets, as a new module loads, keeping `$.state`. */
  const reloaded = async (status: () => string) => {
    const h = harness({ agents: () => [{ id: FORK, description: FORK_DESCRIPTION, type: 'fork', status: status(), spawnedBy: 'to-human' }] })
    await h.present('x')
    forgetPresent()
    return h
  }

  test('the record survives: the fork is still guarded and its end still heard', async () => {
    const h = await reloaded(() => 'running')
    expect(await h.call('Agent', { prompt: 'p' }, FORK)).toEqual({ deny: GUARD_REFUSAL })
    expect(await h.check('Write', { file_path: DRAFT })).toEqual({ decision: 'allow' })
    await h.ended()
    expect(h.commands.some((argv) => argv[2] === 'publish')).toBe(true)
    expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'written', address: ADDRESS } })
  })

  test('a record whose fork the list no longer calls live is closed as not written at the next start, without publishing', async () => {
    let status = 'running'
    const h = await reloaded(() => status)
    status = 'completed'
    await h.start()
    expect(h.commands.some((argv) => argv[2] === 'publish')).toBe(false)
    expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'failed', address: ADDRESS, why: NOT_HEARD } })
    expect(await h.present('again', { id: 'toolu_p2' })).toEqual({ result: STARTED(ADDRESS), context: [FAILED(ADDRESS, NOT_HEARD)] })
  })

  test('a fork the list has dropped is given the grace a lagging list needs, then closed', async () => {
    const h = harness({ agents: () => [] })
    await h.present('x')
    forgetPresent()
    expect(await h.present('again', { id: 'toolu_p2' })).toEqual({ result: STARTED(ADDRESS), context: [FAILED(ADDRESS, NOT_HEARD)] })
    expect(h.sleeps.length).toBeGreaterThan(0)
    expect(h.state.get('presented')).toMatchObject({ toolu_p1: { state: 'failed', why: NOT_HEARD } })
  })

  test('a record whose fork still runs keeps the next call BUSY', async () => {
    const h = await reloaded(() => 'running')
    await h.start()
    expect(await h.present('again', { id: 'toolu_p2' })).toEqual({ deny: BUSY(ADDRESS) })
  })

  test('a reload after the publish committed and before its answer: the next start publishes again and counts the page written', async () => {
    let answer = () => {}
    let first = true
    const h = harness({
      server: {
        publish: () => {
          if (!first) return ok({ ...PUBLISHED, published: false })
          first = false
          return new Promise<Answer>((resolve) => (answer = () => resolve(ok(PUBLISHED))))
        },
      },
    })
    await h.present('x')
    await h.ended()
    // The record says publishing before publish is called.
    expect(h.state.get('present')).toMatchObject({ phase: 'publishing', startedAt: NOW })
    forgetPresent()
    await h.start()
    expect(h.commands.filter((argv) => argv[2] === 'publish')).toHaveLength(2)
    expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'written', address: ADDRESS } })
    expect(h.state.get('present')).toBeNull()
    expect(h.notified).toEqual([`The panel is written: ${ADDRESS}`])
    expect((await h.call('Bash')).context).toEqual([FINISHED(ADDRESS, '').trimEnd()])
    // The first publish's late answer closes nothing again.
    answer()
    await settle()
    expect(h.notified).toHaveLength(1)
    expect(h.failures).toEqual([])
  })

  test('a reload during publishing whose second publish finds nothing written since the run began: not written', async () => {
    let answer = () => {}
    let first = true
    const h = harness({
      server: {
        publish: () => {
          if (!first) return ok({ ...PUBLISHED, published: false, written: NOW - 60_000 })
          first = false
          return new Promise<Answer>((resolve) => (answer = () => resolve(failing('server.py publish: interrupted'))))
        },
      },
    })
    await h.present('x')
    await h.ended()
    forgetPresent()
    await h.start()
    expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'failed', address: ADDRESS, why: 'the fork changed nothing on it' } })
    answer()
    await settle()
  })

  test('a fork whose run closed is still refused after a reload, though the list has dropped it', async () => {
    const h = harness({ agents: () => [] })
    await h.present('x')
    await h.ended()
    forgetPresent()
    expect(await h.check('Write', { file_path: '/w/README.md', content: 'x' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.call('Agent', { prompt: 'p' }, FORK)).toEqual({ deny: GUARD_REFUSAL })
  })

  test("a reload whose record, rows and notices cannot be read still guards the open run's fork, by the ids kept apart", async () => {
    const unreadable = new Set<string>()
    const h = harness({ unreadable, agents: () => [] })
    await h.present('x')
    forgetPresent()
    for (const key of ['present', 'presented', 'presentNotice']) unreadable.add(key)
    expect(await h.check('Write', { file_path: '/w/README.md', content: 'x' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.call('Agent', { prompt: 'p' }, FORK)).toEqual({ deny: GUARD_REFUSAL })
  })

  test('with the kept ids unreadable too, the list names the panel fork, and the guard holds it', async () => {
    const unreadable = new Set<string>()
    const h = harness({ unreadable })
    await h.present('x')
    forgetPresent()
    for (const key of ['present', 'presented', 'presentNotice', 'presentForks']) unreadable.add(key)
    expect(await h.check('Write', { file_path: '/w/README.md', content: 'x' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.call('Agent', { prompt: 'p' }, FORK)).toEqual({ deny: GUARD_REFUSAL })
  })

  test('with the kept ids unreadable, an agent the list names as no panel fork passes', async () => {
    const h = harness({
      unreadable: new Set(['presentForks']),
      agents: () => [{ id: 'other', description: 'tests', type: 'general-purpose', status: 'running' }],
    })
    expect(await h.check('Write', { file_path: '/w/x' }, { agentId: 'other' })).toEqual({ decision: 'ask' })
    expect(await h.call('Bash', {}, 'other')).toEqual({ result: 'ran' })
  })

  test("a former panel fork's call, after a reload with the kept ids unreadable and the list empty, is refused at the call and at the check", async () => {
    const unreadable = new Set<string>()
    const h = harness({ unreadable, agents: () => [], failsClosed: true })
    await h.present('x')
    await h.ended()
    forgetPresent()
    unreadable.add('presentForks')
    expect(await h.call('Write', { file_path: '/w/README.md', content: 'x' }, FORK)).toEqual({ deny: GUARD_REFUSAL })
    expect(await h.check('Write', { file_path: '/w/README.md', content: 'x' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    // Read back at the next call: then the kept ids say who it is.
    unreadable.delete('presentForks')
    expect(await h.check('Write', { file_path: '/w/README.md', content: 'x' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.check('Write', { file_path: '/w/x' }, { agentId: 'other', core: 'allow' })).toEqual({ decision: 'allow' })
  })

  test('every fork id is kept: with 201 runs behind it, the oldest fork is still held after a reload', async () => {
    let n = 0
    const h = harness({ agents: () => [], spawn: () => ({ model: 'claude-haiku', agentId: `fork-${n++}` }) })
    for (let i = 0; i < 201; i++) {
      await h.present('x', { id: `toolu_${i}` })
      await h.ended({ agentId: `fork-${i}` })
    }
    expect((h.state.get('presentForks') as string[]).length).toBe(201)
    forgetPresent()
    expect(await h.check('Write', { file_path: '/w/x' }, { agentId: 'fork-0', core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.call('Agent', {}, 'fork-0')).toEqual({ deny: GUARD_REFUSAL })
  })

  test("with the kept ids and the list both unreadable, a subagent's call is refused: who it is cannot be told", async () => {
    const h = harness({
      failsClosed: true,
      unreadable: new Set(['present', 'presented', 'presentNotice', 'presentForks']),
      agents: () => {
        throw new Error('the agent list is not answering')
      },
    })
    expect(await h.check('Write', { file_path: '/w/x' }, { agentId: 'someone', core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.call('Bash', {}, 'someone')).toEqual({ deny: GUARD_REFUSAL })
    // The main loop's calls are no fork's, whatever can be read.
    expect(await h.check('Write', { file_path: '/w/x' }, { agentId: '' })).toEqual({ decision: 'ask' })
    expect(await h.call('Bash')).toEqual({ result: 'ran' })
  })

  test('kept ids that could not be read are read again, and no write in between loses one', async () => {
    const unreadable = new Set<string>()
    const h = harness({ unreadable, agents: () => [], failsClosed: true })
    await h.present('x')
    await h.ended()
    forgetPresent()
    unreadable.add('presentForks')
    // An agent the list does not name may be a closed panel fork: refused while the ids are unread.
    expect(await h.check('Write', { file_path: '/w/x' }, { agentId: 'other', core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    // A notice taken meanwhile writes the record, and leaves the ids as they were.
    await h.call('Bash')
    expect(h.state.get('presentForks')).toEqual([FORK])
    unreadable.delete('presentForks')
    expect(await h.check('Write', { file_path: '/w/x' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.check('Write', { file_path: '/w/x' }, { agentId: 'other', core: 'allow' })).toEqual({ decision: 'allow' })
  })

  test('a write queued before the record was read back does not store its stale snapshot over the record', async () => {
    const open = { agentId: FORK, toolUseId: 'toolu_p0', session: SESSION, dir: ROOT, draft: DRAFT, address: ADDRESS, update: 2, startedAt: NOW, phase: 'writing' }
    const unreadable = new Set(['present'])
    const stalled = new Set(['presentNotice'])
    const h = harness({ unreadable, stalled })
    h.state.set('present', open)
    h.state.set('presentForks', [FORK])
    h.state.set('presentNotice', [FAILED(ADDRESS, 'an earlier run')])
    // The record cannot be read; a prompt dropped beneath takes the notice and gives it back: two writes, the first stalled.
    expect((await h.prompt('one', true)).context).toEqual([FAILED(ADDRESS, 'an earlier run')])
    // The record reads back at a later call, which finds its fork running.
    unreadable.delete('present')
    expect(await h.present('x', { id: 'toolu_p1' })).toEqual({ deny: BUSY(ADDRESS) })
    await h.release()
    expect(h.state.get('present')).toEqual(open)
    // A module after this one still finds the run open.
    forgetPresent()
    expect(await h.present('x', { id: 'toolu_p2' })).toEqual({ deny: BUSY(ADDRESS) })
    expect(h.spawned).toEqual([])
  })

  test('a publishing phase that cannot be kept publishes nothing: not written, and the next call is not BUSY', async () => {
    const unwritable = new Set<string>()
    const h = harness({ unwritable })
    await h.present('x')
    unwritable.add('present')
    await h.ended()
    expect(h.commands.some((argv) => argv[2] === 'publish')).toBe(false)
    const why = 'its record could not be kept'
    expect(h.state.get('presented')).toEqual({ toolu_p1: { state: 'failed', address: ADDRESS, why } })
    expect(h.notified).toEqual([`The panel was not written (${why})`])
    unwritable.delete('present')
    expect(await h.present('again', { id: 'toolu_p2' })).toEqual({ result: STARTED(ADDRESS), context: [FAILED(ADDRESS, why)] })
  })

  test('a notice not yet delivered is delivered by the module after', async () => {
    const h = harness()
    await h.present('x')
    await h.ended()
    forgetPresent()
    expect((await h.call('Bash')).context).toEqual([FINISHED(ADDRESS, SAID)])
  })
})

describe("the guard over the fork's calls", () => {
  const running = async (links: Record<string, string | null> = {}) => {
    const h = harness({ links })
    await h.present('x')
    return h
  }

  for (const tool of ['Agent', 'Workflow', 'NotebookEdit', 'SendMessage', 'WebFetch', 'TaskStop', MESSAGE_TOOL, 'mcp__sminos__AskUserQuestion']) {
    test(`${tool} is refused by name at tool.call, nothing beneath run`, async () => {
      const h = await running()
      let ran = false
      expect(await h.call(tool, {}, FORK, () => ((ran = true), { result: 'ran' }))).toEqual({ deny: GUARD_REFUSAL })
      expect(ran).toBe(false)
    })
  }

  test("the fork's own present call is refused by the guard, before the handler", async () => {
    const h = await running()
    expect(await h.present('again', { agentId: FORK, id: 'toolu_p2' })).toEqual({ deny: GUARD_REFUSAL })
    expect(h.spawned).toHaveLength(1)
  })

  test('Read, Grep, Glob, Bash, Write and Edit go on at tool.call', async () => {
    const h = await running()
    for (const tool of ['Read', 'Grep', 'Glob', 'Bash', 'Write', 'Edit']) {
      expect(await h.call(tool, { file_path: DRAFT, content: 'x', new_string: 'y' }, FORK)).toEqual({ result: 'ran' })
    }
  })

  test('Read, Grep and Glob are allowed at tool.check over an ask beneath', async () => {
    const h = await running()
    for (const tool of ['Read', 'Grep', 'Glob']) {
      expect(await h.check(tool, { file_path: '/etc/hosts' })).toEqual({ decision: 'allow' })
    }
  })

  test('Bash is allowed when the engine holds it read-only, denied otherwise, over core allow and ask alike', async () => {
    const h = await running()
    expect(await h.check('Bash', { command: 'git log -1' }, { isReadOnly: true })).toEqual({ decision: 'allow' })
    expect(await h.check('Bash', { command: 'touch x' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.check('Bash', { command: 'echo > x' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
  })

  test("Write and Edit of the draft are allowed over the protected location's ask", async () => {
    const h = await running()
    expect(await h.check('Write', { file_path: DRAFT, content: '<p>x</p>' })).toEqual({ decision: 'allow' })
    expect(await h.check('Edit', { file_path: DRAFT, old_string: 'a', new_string: 'b' })).toEqual({ decision: 'allow' })
  })

  test('a path outside the draft, the page beside it, a link elsewhere and a path that lands nowhere are denied; .. onto the draft is the draft', async () => {
    const h = await running({
      [`${ROOT}/../b4d10f41/draft.html`]: DRAFT,
      '/w/innocent.html': '/w/README.md',
      [`${ROOT}/sneaky.html`]: '/w/README.md',
      [`${ROOT}/../elsewhere/draft.html`]: '/cfg/to-human/panels/elsewhere/draft.html',
      '/w/missing.html': null,
    })
    for (const path of ['/w/README.md', `${ROOT}/panel.html`, '/w/innocent.html', `${ROOT}/sneaky.html`, `${ROOT}/../elsewhere/draft.html`, '/w/missing.html', '']) {
      expect(await h.check('Write', { file_path: path, content: 'x' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    }
    expect(await h.check('Write', { content: 'x' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.check('Write', { file_path: `${ROOT}/../b4d10f41/draft.html`, content: 'x' })).toEqual({ decision: 'allow' })
  })

  test('a draft that is itself reached through a link is matched by where it lands', async () => {
    const h = await running({ [DRAFT]: '/private/cfg/to-human/panels/b4d10f41/draft.html', '/private/cfg/to-human/panels/b4d10f41/draft.html': '/private/cfg/to-human/panels/b4d10f41/draft.html' })
    expect(await h.check('Write', { file_path: DRAFT })).toEqual({ decision: 'allow' })
    expect(await h.check('Write', { file_path: '/private/cfg/to-human/panels/b4d10f41/draft.html' })).toEqual({ decision: 'allow' })
  })

  test('any other tool that reaches tool.check is denied: none is left to core', async () => {
    const h = await running()
    expect(await h.check('NotebookEdit', { notebook_path: '/w/a.ipynb' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
  })

  test("a write holding a secret's handle is refused at tool.call, before a hook beneath restores it", async () => {
    const h = await running()
    const reached: Event[] = []
    // As devcloud's secrets guard, beneath: the handle restored to the secret's bytes in the input it passes on.
    const restoring = (e: Event) => {
      const restored = JSON.parse(JSON.stringify(e).replaceAll('[secret:API_KEY]', 'sk-live-0123')) as Event
      reached.push(restored)
      return { result: 'written' }
    }
    expect(await h.call('Write', { file_path: DRAFT, content: 'key [secret:API_KEY]' }, FORK, restoring)).toEqual({ deny: GUARD_REFUSAL })
    expect(await h.call('Edit', { file_path: DRAFT, old_string: 'a', new_string: 'b [redacted:TOKEN]' }, FORK, restoring)).toEqual({ deny: GUARD_REFUSAL })
    expect(reached).toEqual([])
    expect(await h.call('Write', { file_path: DRAFT, content: '<p>plain</p>' }, FORK, restoring)).toEqual({ result: 'written' })
  })

  test("the main loop's calls and another agent's pass untouched", async () => {
    const h = await running()
    expect(await h.check('Write', { file_path: '/w/x' }, { agentId: '' })).toEqual({ decision: 'ask' })
    expect(await h.check('Write', { file_path: '/w/x' }, { agentId: 'other' })).toEqual({ decision: 'ask' })
    expect(await h.call('Agent', {}, 'other')).toEqual({ result: 'ran' })
    expect(await h.call('Agent')).toEqual({ result: 'ran' })
  })

  test("the engine's check of this plugin's own spawn is allowed; the same call from anyone else is the engine's to judge", async () => {
    const h = harness()
    const spawn = { prompt: 'p', description: FORK_DESCRIPTION, run_in_background: true, subagent_type: 'fork' }
    const own = { agentId: '', origin: { plugin: 'to-human', tier: 'user' } }
    expect(await h.check('Agent', spawn, own)).toEqual({ decision: 'allow' })
    expect(await h.check('Agent', spawn, { agentId: '' })).toEqual({ decision: 'ask' })
    expect(await h.check('Agent', spawn, { ...own, origin: { plugin: 'sminos', tier: 'user' } })).toEqual({ decision: 'ask' })
    expect(await h.check('Agent', { ...spawn, description: 'other' }, own)).toEqual({ decision: 'ask' })
    expect(await h.check('Agent', { ...spawn, subagent_type: 'general-purpose' }, own)).toEqual({ decision: 'ask' })
    expect(await h.check('Bash', { command: 'ls' }, own)).toEqual({ decision: 'ask' })
  })

  test("a failure beneath a main-loop call is not read as the guard's", async () => {
    const h = await running()
    const failingCore = () => {
      throw new Error('the tool broke')
    }
    await expect(h.call('Bash', {}, undefined, failingCore)).rejects.toThrow('the tool broke')
  })

  test("a former fork's Write or Edit of the open run's draft is denied; the open run's fork is allowed", async () => {
    let n = 0
    const h = harness({ agents: () => [], spawn: () => ({ model: 'claude-haiku', agentId: `fork-${n++}` }) })
    await h.present('x', { id: 'toolu_p1' })
    await h.ended({ agentId: 'fork-0' })
    await h.present('y', { id: 'toolu_p2' })
    // The new run's draft is the same file: a late call of the old fork must not write what the new fork's end publishes.
    for (const [tool, input] of [['Write', { file_path: DRAFT, content: 'x' }], ['Edit', { file_path: DRAFT, old_string: 'a', new_string: 'b' }]] as const) {
      expect(await h.check(tool, input, { agentId: 'fork-0', core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
      expect(await h.check(tool, input, { agentId: 'fork-1' })).toEqual({ decision: 'allow' })
    }
    // So after a reload, from the kept record and ids.
    forgetPresent()
    expect(await h.check('Write', { file_path: DRAFT }, { agentId: 'fork-0', core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.check('Write', { file_path: DRAFT }, { agentId: 'fork-1' })).toEqual({ decision: 'allow' })
  })

  test("after a reload, a run kept as publishing holds its fork's draft write: the fork has ended", async () => {
    const h = harness()
    h.state.set('present', { agentId: FORK, toolUseId: 'toolu_p1', session: SESSION, dir: ROOT, draft: DRAFT, address: ADDRESS, update: 2, startedAt: NOW, phase: 'publishing' })
    h.state.set('presentForks', [FORK])
    expect(await h.check('Write', { file_path: DRAFT, content: 'x' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.check('Edit', { file_path: DRAFT, old_string: 'a', new_string: 'b' }, { core: 'allow' })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
  })

  test('a fork still refused after its run closed: its writes go nowhere', async () => {
    const h = await running()
    await h.ended()
    expect(await h.check('Write', { file_path: DRAFT })).toEqual({ decision: 'deny', reason: GUARD_REFUSAL })
    expect(await h.call('Agent', {}, FORK)).toEqual({ deny: GUARD_REFUSAL })
  })
})

describe("the call's row in the report", () => {
  const PRESENTED = { plugin: 'to-human', key: 'presented' } as const
  const props = (extra: Record<string, unknown> = {}) => ({
    tool_use_id: 'toolu_p1',
    tool: PRESENT_TOOL,
    input: { brief: 'Two options for the cache.\nMore below.' },
    isRunning: false,
    isErrored: false,
    isInterrupted: false,
    output: STARTED(ADDRESS),
    ...extra,
  })
  const mounted = ($: Engine, extra: Record<string, unknown> = {}) =>
    $.ui.mount({ plugin: 'to-human', surface: 'terminal', component: 'ToolUse', requestId: 'toolu_p1', props: props(extra) } as never)
  const view = (on: On, presented?: unknown) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({ type: 'Text', children: [`engine ${e.component}`] }))
    if (presented !== undefined) {
      on('state.get', { plugin: 'to-human', key: 'presented' }, () => ({ value: { value: presented, version: 1 } }) as never)
    }
  }

  test('writing: the brief\'s first line, then writing…', async ($, on) => {
    view(on, { toolu_p1: { state: 'writing', address: ADDRESS } })
    const row = await mounted($)
    expect(await row.find({ type: 'Text', text: '● panel' })).toBeDefined()
    expect(await row.find({ type: 'Text', text: 'Two options for the cache.' })).toBeDefined()
    expect(await row.find({ type: 'Text', text: 'writing…' })).toBeDefined()
    expect(await row.find({ type: 'Text', text: 'More below.' })).toBeUndefined()
    expect(await row.find({ type: 'Text', text: 'engine ToolUse' })).toBeUndefined()
  })

  test('written: the address as a link', async ($, on) => {
    view(on, { toolu_p1: { state: 'written', address: ADDRESS } })
    const row = await mounted($)
    expect((await row.find({ type: 'Link' }))?.props.href).toBe(ADDRESS)
    expect(await row.find({ type: 'Text', text: 'writing…' })).toBeUndefined()
  })

  test('not written, and why', async ($, on) => {
    view(on, { toolu_p1: { state: 'failed', address: ADDRESS, why: 'the fork changed nothing on it' } })
    const row = await mounted($)
    expect(await row.find({ type: 'Text', text: 'not written: the fork changed nothing on it' })).toBeDefined()
    expect(await row.find({ type: 'Link' })).toBeUndefined()
  })

  test('with no state (a resumed session): the address its result carries', async ($, on) => {
    view(on)
    const row = await mounted($)
    expect((await row.find({ type: 'Link' }))?.props.href).toBe(ADDRESS)
  })

  test('its result row draws nothing', async ($, on) => {
    view(on)
    const result = await $.ui.mount({
      plugin: 'to-human', surface: 'terminal', component: 'ToolResult', requestId: 'toolu_p1',
      props: { tool_use_id: 'toolu_p1', tool: PRESENT_TOOL, output: STARTED(ADDRESS), isErrored: false },
    } as never)
    expect(await result.find({ type: 'Text' })).toBeUndefined()
  })

  test('a refused call stays working record, as the engine draws it', async ($, on) => {
    view(on)
    const row = await mounted($, { isErrored: true, output: BUSY(ADDRESS) })
    expect(await row.find({ type: 'Text', text: '● panel' })).toBeUndefined()
  })

  test('the ctrl+o transcript keeps the engine\'s row', async ($, on) => {
    view(on)
    const row = await mounted($, { isExpanded: true })
    expect(await row.find({ type: 'Text', text: 'engine ToolUse' })).toBeDefined()
  })
})

describe('a present call beside a final message', () => {
  test('keeps the request after it, as any other tool call does', () => {
    const since = note({ calls: 0, finals: 0, sent: 0, isOther: false }, 'response', {
      role: 'assistant',
      content: [
        { type: 'tool_use', id: 'm', name: MESSAGE_TOOL, input: { text: 'Done.', final: true } },
        { type: 'tool_use', id: 'p', name: PRESENT_TOOL, input: { brief: 'x' } },
      ] as never,
    })
    expect(endsOnFinal(since)).toBe(false)
  })
})

describe('the harness', () => {
  test('no hook failed in any flow above but where the test meant the guard to refuse what it could not place', () => {
    expect(harnesses.length).toBeGreaterThan(0)
    expect(harnesses.filter((h) => !h.failsClosed).flatMap((h) => h.failures)).toEqual([])
    expect(harnesses.filter((h) => h.failsClosed).flatMap((h) => h.failures).every((f) => f.includes('Unresolved'))).toBe(true)
  })
})
