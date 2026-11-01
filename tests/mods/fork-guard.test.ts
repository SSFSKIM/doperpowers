import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import { FORK_GUARD_PRESENT, FORK_GUARD_PROBE, FORK_GUARD_REASON, FORK_TOOLS, registerForkGuard, resetForkGuard } from '../../hooks/mods/fork-guard'
import { register } from '../../hooks/mods/register'

tier('user')

type Handler = (...args: unknown[]) => unknown
type Registration = { event: string; matcher?: Record<string, unknown>; handler: Handler; caught?: Handler; mod: string }

const FORK = 'afork0000000001'
const MANAGED = { id: FORK, description: 'manager query', type: 'fork', status: 'running', spawnedBy: 'sminos' }

/**
 * The hooks a register function registers, each with the `.catch` it carries,
 * in order: the first registered is the outermost, as the engine runs one
 * module's hooks.
 */
function collect(registerAll: (on: On) => void, mod = 'doperpowers') {
  const hooks: Registration[] = []
  const on = ((event: string, ...rest: unknown[]) => {
    const r: Registration = { event, handler: rest[rest.length - 1] as Handler, matcher: rest.length > 1 ? (rest[0] as Record<string, unknown>) : undefined, mod }
    hooks.push(r)
    return {
      catch: (h: Handler) => {
        r.caught = h
      },
    }
  }) as unknown as On
  registerAll(on)
  return hooks
}

const matches = (r: Registration, event: string, e: Record<string, unknown>) =>
  r.event === event && Object.entries(r.matcher ?? {}).every(([k, v]) => (v instanceof RegExp ? v.test(String(e[k])) : e[k] === v))

/**
 * An engine of plain records: `$.agent.list()` answers `agents` (or rejects
 * while `listFails`), counted; and a chain runner that runs each matching
 * hook outermost first, as the engine does, with a failed hook's `.catch`
 * asked in its place (`next.called` saying whether it had called beneath),
 * down to `core` at the bottom.
 */
function engine(options: { agents?: Record<string, unknown>[] } = {}) {
  let agents = options.agents ?? [MANAGED]
  let listFails = false
  let lists = 0
  const $ = {
    agent: {
      list: async () => {
        lists++
        if (listFails) {
          throw new Error('$.agent.list: the host did not answer')
        }
        return agents.map((a) => ({ ...a }))
      },
    },
  } as unknown as EngineInterface
  const run = async (hooks: Registration[], event: string, e: Record<string, unknown>, core: () => unknown, origin = { plugin: 'engine', tier: 'core' }): Promise<unknown> => {
    const chain = hooks.filter((r) => matches(r, event, e))
    const at = async (i: number, input: Record<string, unknown>): Promise<unknown> => {
      const r = chain[i]
      if (r === undefined) {
        return core()
      }
      let called = false
      const next = Object.assign(
        (inner: Record<string, unknown>) => {
          called = true
          return at(i + 1, inner)
        },
        { origin, trace: [] },
      )
      try {
        return await r.handler($, input, next)
      } catch (error) {
        if (r.caught === undefined) {
          return at(i + 1, input)
        }
        return r.caught($, input, Object.assign(next, { called, error: { kind: 'throw', message: String(error) } }))
      }
    }
    return at(0, e)
  }
  return {
    $,
    run,
    lists: () => lists,
    setAgents: (list: Record<string, unknown>[]) => (agents = list),
    failLists: (fails: boolean) => (listFails = fails),
  }
}

/** A call a loop makes, as `tool.call` carries it: the tool, its id, its arguments beside them, the loop (null: the main loop's). */
const call = (tool: string, input: Record<string, unknown> = {}, agentId: string | null = FORK) => ({
  tool,
  tool_use_id: `toolu_${tool}`,
  ...input,
  ...(agentId !== null && { agentId }),
})
/** The permission decision for a call, as `tool.check` carries it. */
const check = (tool: string, input: unknown = {}, agentId: string | null = FORK, isReadOnly = false) => ({
  tool,
  input,
  tool_use_id: `toolu_${tool}`,
  ...(agentId !== null && { agentId }),
  ...(isReadOnly && { isReadOnly: true }),
})

describe('the read-only fork guard: its words', () => {
  test('a fork may call the read tools and Bash, refused anything else in these words', () => {
    expect([...FORK_TOOLS]).toEqual(['Read', 'Grep', 'Glob', 'Bash'])
    expect(FORK_GUARD_REASON).toBe('This is a read-only fork (manager query): calls that change files or state are refused.')
  })

  test("the presence probe's path and answer are the bridge's, word for word (sminos/hooks/mods/bridge-ask.tsx)", () => {
    expect(FORK_GUARD_PROBE).toBe('/dev/null/sminos-fork-guard-probe')
    expect(FORK_GUARD_PRESENT).toBe('The read-only fork guard (doperpowers) is loaded.')
  })
})

describe("the read-only fork guard: a managed fork's calls", () => {
  for (const tool of ['Agent', 'SendMessage', 'Write', 'Edit', 'NotebookEdit', 'Workflow', 'mcp__web__fetch', 'mcp__to-human__message']) {
    test(`${tool} is refused at tool.call, nothing beneath run`, async () => {
      resetForkGuard()
      const eng = engine()
      let ran = false
      const result = await eng.run(collect(registerForkGuard), 'tool.call', call(tool), () => {
        ran = true
        return { text: 'ran' }
      })
      expect(result).toEqual({ deny: FORK_GUARD_REASON })
      expect(ran).toBe(false)
    })
  }

  test("a plugin's tool served in its own tool.call hook, beneath the guard, never runs: its probe file is not written", async () => {
    resetForkGuard()
    const eng = engine()
    const written: string[] = []
    const standIn = collect((on) => {
      on('tool.call', { tool: 'mcp__probe__write' }, async () => {
        written.push('/tmp/fork-guard-probe')
        return { result: 'written' }
      })
    }, 'probe')
    const result = await eng.run([...collect(registerForkGuard), ...standIn], 'tool.call', call('mcp__probe__write', { path: '/tmp/fork-guard-probe' }), () => ({ text: 'core' }))
    expect(result).toEqual({ deny: FORK_GUARD_REASON })
    expect(written).toEqual([])
  })

  test('Read, Grep, Glob and Bash go on to the permission check at tool.call', async () => {
    resetForkGuard()
    const eng = engine()
    for (const tool of FORK_TOOLS) {
      expect(await eng.run(collect(registerForkGuard), 'tool.call', call(tool), () => ({ text: `${tool} ran` }))).toEqual({ text: `${tool} ran` })
    }
  })

  test('at tool.check the read tools are allowed, so the fork raises no permission prompt in the session', async () => {
    resetForkGuard()
    const eng = engine()
    for (const tool of ['Read', 'Grep', 'Glob']) {
      let asked = false
      const verdict = await eng.run(collect(registerForkGuard), 'tool.check', check(tool, { file_path: '/etc/hosts' }), () => {
        asked = true
        return { decision: 'ask' }
      })
      expect(verdict).toEqual({ decision: 'allow' })
      expect(asked).toBe(false)
    }
  })

  test('Bash is allowed when the engine holds the input read-only, denied otherwise, over core allow and ask alike', async () => {
    resetForkGuard()
    const eng = engine()
    const hooks = collect(registerForkGuard)
    expect(await eng.run(hooks, 'tool.check', check('Bash', { command: 'git log -1' }, FORK, true), () => ({ decision: 'ask' }))).toEqual({ decision: 'allow' })
    expect(await eng.run(hooks, 'tool.check', check('Bash', { command: 'touch /tmp/x' }), () => ({ decision: 'allow' }))).toEqual({ decision: 'deny', reason: FORK_GUARD_REASON })
    expect(await eng.run(hooks, 'tool.check', check('Bash', { command: 'echo hi > /tmp/x' }), () => ({ decision: 'ask' }))).toEqual({ decision: 'deny', reason: FORK_GUARD_REASON })
  })

  test('any other tool that reaches tool.check is denied as well', async () => {
    resetForkGuard()
    const eng = engine()
    expect(await eng.run(collect(registerForkGuard), 'tool.check', check('Write', { file_path: '/tmp/x' }), () => ({ decision: 'allow' }))).toEqual({
      decision: 'deny',
      reason: FORK_GUARD_REASON,
    })
  })

  test("an agent's verdict, once resolved, is remembered: one list read for its every call", async () => {
    resetForkGuard()
    const eng = engine()
    const hooks = collect(registerForkGuard)
    await eng.run(hooks, 'tool.call', call('Read'), () => ({ text: 'ok' }))
    await eng.run(hooks, 'tool.check', check('Read'), () => ({ decision: 'ask' }))
    await eng.run(hooks, 'tool.call', call('Agent'), () => ({ text: 'ok' }))
    expect(eng.lists()).toBe(1)
  })
})

describe('the read-only fork guard: fails closed', () => {
  test("a subagent's call is refused while the agent list rejects, and looked for again once it answers", async () => {
    resetForkGuard()
    const eng = engine({ agents: [{ id: 'aother', description: 'x', type: 'general-purpose', status: 'running' }] })
    const hooks = collect(registerForkGuard)
    eng.failLists(true)
    expect(await eng.run(hooks, 'tool.call', call('Read', {}, 'aother'), () => ({ text: 'ran' }))).toEqual({ deny: FORK_GUARD_REASON })
    expect(await eng.run(hooks, 'tool.check', check('Read', {}, 'aother'), () => ({ decision: 'allow' }))).toEqual({ decision: 'deny', reason: FORK_GUARD_REASON })
    eng.failLists(false)
    expect(await eng.run(hooks, 'tool.call', call('Write', {}, 'aother'), () => ({ text: 'ran' }))).toEqual({ text: 'ran' })
  })

  test('each registration carries a .catch that refuses a call it had not passed on, and replays one it had', async () => {
    resetForkGuard()
    const hooks = collect(registerForkGuard).filter((r) => r.event === 'tool.call' || r.event === 'tool.check')
    expect(hooks.map((r) => r.event).sort()).toEqual(['tool.call', 'tool.check'])
    const eng = engine()
    for (const r of hooks) {
      expect(r.caught).toBeDefined()
      const e = r.event === 'tool.call' ? call('Read') : check('Read')
      const notCalled = Object.assign(async () => ({ passed: true }), { called: false, origin: { plugin: 'engine', tier: 'core' } })
      expect(await r.caught!(eng.$, e, notCalled)).toEqual(r.event === 'tool.call' ? { deny: FORK_GUARD_REASON } : { decision: 'deny', reason: FORK_GUARD_REASON })
      const called = Object.assign(async () => ({ passed: true }), { called: true, origin: { plugin: 'engine', tier: 'core' } })
      expect(await r.caught!(eng.$, e, called)).toEqual({ passed: true })
    }
  })

  test('a handler that throws before passing the call on is refused by its .catch', async () => {
    resetForkGuard()
    const eng = engine()
    // A list that answers something no agent list is: the lookup throws.
    ;(eng.$ as unknown as { agent: { list: () => Promise<unknown> } }).agent.list = async () => ({ not: 'a list' })
    const hooks = collect(registerForkGuard)
    expect(await eng.run(hooks, 'tool.call', call('Read'), () => ({ text: 'ran' }))).toEqual({ deny: FORK_GUARD_REASON })
    expect(await eng.run(hooks, 'tool.check', check('Read'), () => ({ decision: 'allow' }))).toEqual({ decision: 'deny', reason: FORK_GUARD_REASON })
  })
})

describe('the read-only fork guard: everything else untouched', () => {
  test("another plugin's fork, sminos's non-fork subagent, and the model's own subagent keep their tools", async () => {
    resetForkGuard()
    const eng = engine({
      agents: [
        { id: 'aprobe', description: 'fork probe', type: 'fork', status: 'running', spawnedBy: 'forkprobe' },
        { id: 'asminos', description: 'x', type: 'general-purpose', status: 'running', spawnedBy: 'sminos' },
        { id: 'amodel', description: 'y', type: 'fork', status: 'running' },
      ],
    })
    const hooks = collect(registerForkGuard)
    for (const id of ['aprobe', 'asminos', 'amodel']) {
      expect(await eng.run(hooks, 'tool.call', call('Write', {}, id), () => ({ text: 'wrote' }))).toEqual({ text: 'wrote' })
      expect(await eng.run(hooks, 'tool.check', check('Write', {}, id), () => ({ decision: 'ask' }))).toEqual({ decision: 'ask' })
    }
  })

  test('the main loop passes untouched, with no lookup', async () => {
    resetForkGuard()
    const eng = engine()
    const hooks = collect(registerForkGuard)
    expect(await eng.run(hooks, 'tool.call', call('Write', {}, null), () => ({ text: 'wrote' }))).toEqual({ text: 'wrote' })
    expect(await eng.run(hooks, 'tool.check', check('Bash', { command: 'rm x' }, null), () => ({ decision: 'ask' }))).toEqual({ decision: 'ask' })
    expect(eng.lists()).toBe(0)
  })

  test("a loop the list does not name passes, since the engine lists no workflow agent or engine fork while it lists a bridge fork from its spawn on; it is looked for again at its next call", async () => {
    resetForkGuard()
    const eng = engine()
    const hooks = collect(registerForkGuard)
    expect(await eng.run(hooks, 'tool.call', call('Write', {}, 'aworkflow'), () => ({ text: 'wrote' }))).toEqual({ text: 'wrote' })
    expect(await eng.run(hooks, 'tool.check', check('Write', {}, 'aworkflow'), () => ({ decision: 'ask' }))).toEqual({ decision: 'ask' })
    expect(eng.lists()).toBe(2)
    // Should a managed fork's listing ever come late, its next call finds it.
    eng.setAgents([MANAGED, { ...MANAGED, id: 'alate' }])
    expect(await eng.run(hooks, 'tool.call', call('Write', {}, 'alate'), () => ({ text: 'wrote' }))).toEqual({ deny: FORK_GUARD_REASON })
  })
})

describe('the read-only fork guard: its presence, as the bridge asks it', () => {
  const probe = { tool: 'Read', input: { file_path: FORK_GUARD_PROBE } }

  test("sminos's query for the probe path is answered with the guard's own words; nothing beneath runs", async () => {
    resetForkGuard()
    const eng = engine()
    let asked = false
    const verdict = await eng.run(collect(registerForkGuard), 'tool.check', probe, () => {
      asked = true
      return { decision: 'allow' }
    }, { plugin: 'sminos', tier: 'user' })
    expect(verdict).toEqual({ decision: 'deny', reason: FORK_GUARD_PRESENT })
    expect(asked).toBe(false)
    expect(eng.lists()).toBe(0)
  })

  test("the same path asked by another plugin, or on a real call, is an ordinary check", async () => {
    resetForkGuard()
    const eng = engine()
    const hooks = collect(registerForkGuard)
    expect(await eng.run(hooks, 'tool.check', probe, () => ({ decision: 'allow' }), { plugin: 'web', tier: 'user' })).toEqual({ decision: 'allow' })
    expect(await eng.run(hooks, 'tool.check', { ...probe, tool_use_id: 'toolu_1' }, () => ({ decision: 'allow' }), { plugin: 'sminos', tier: 'user' })).toEqual({ decision: 'allow' })
  })
})

describe('the read-only fork guard: its place in the plugin', () => {
  test("registered ahead of the appeal: a managed fork's write is refused before the appeal's pass, or anything beneath, can apply", async () => {
    resetForkGuard()
    const hooks = collect(register)
    const guard = collect(registerForkGuard)
    // The plugin's outermost tool.call and tool.check hooks are the guard's.
    for (const event of ['tool.call', 'tool.check']) {
      expect(String(hooks.find((r) => r.event === event)!.handler)).toBe(String(guard.find((r) => r.event === event)!.handler))
    }
    const eng = engine()
    let core = false
    const verdict = await eng.run(hooks, 'tool.check', check('Bash', { command: 'git push --force' }), () => {
      core = true
      return { decision: 'ask' }
    })
    expect(verdict).toEqual({ decision: 'deny', reason: FORK_GUARD_REASON })
    expect(core).toBe(false)
  })
})
