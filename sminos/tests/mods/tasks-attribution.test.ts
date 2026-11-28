import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import { registerTaskAttribution } from '../../hooks/mods/tasks'

tier('user')

// Every id and name here is invented.
const ID = 'a1b2c3d4e5f60718'
const ASSIGN = "task assign-human --class blocking --title 'Log in' --body-file - <<'EOF'\nOpen it.\nEOF"

type Handler = ($: EngineInterface, e: Record<string, unknown>, next: (e: Record<string, unknown>) => Promise<unknown>) => Promise<unknown>
type Catch = ($: EngineInterface, e: Record<string, unknown>, next: (e: Record<string, unknown>) => Promise<unknown>) => Promise<unknown>

/** The hook as registered, its failure handler, and an engine whose agent list and env the test sets. */
function harness(options: { agents?: { id: string; description: string; type: string }[] | Error; env?: Record<string, string> } = {}) {
  const hooks: { event: string; matcher: unknown; handler: Handler; caught?: Catch }[] = []
  const on = ((event: string, matcher: unknown, handler: Handler) => {
    const hook: (typeof hooks)[number] = { event, matcher, handler }
    hooks.push(hook)
    return {
      catch: (caught: Catch) => {
        hook.caught = caught
      },
    }
  }) as unknown as On
  registerTaskAttribution(on)
  let listed = 0
  const $ = {
    env: { get: async (name: string) => options.env?.[name] },
    agent: {
      list: async () => {
        listed += 1
        if (options.agents instanceof Error) throw options.agents
        return (options.agents ?? []).map((a) => ({ ...a, status: 'running' }))
      },
    },
  } as unknown as EngineInterface
  const call = async (e: Record<string, unknown>) => {
    const ran: Record<string, unknown>[] = []
    const next = async (passed: Record<string, unknown>) => {
      ran.push(passed)
      return { result: { stdout: 'ok' } }
    }
    const result = await hooks[0]!.handler($, e, next)
    return { result, ran }
  }
  return { hooks, call, $, listed: () => listed }
}

describe('the attribution hook', () => {
  test('it is one Bash hook with a failure handler', () => {
    const h = harness()
    expect(h.hooks.map((x) => [x.event, x.matcher])).toEqual([['tool.call', { tool: 'Bash' }]])
    expect(h.hooks[0]!.caught).toBeDefined()
  })

  test("a subagent's assign goes on with the flag, named from the agent list, and returns what the call returned", async () => {
    const h = harness({ agents: [{ id: ID, description: 'Review the diff', type: 'general-purpose' }] })
    const { result, ran } = await h.call({ tool: 'Bash', tool_use_id: 'toolu_1', agentId: ID, command: ASSIGN })
    expect(ran).toEqual([{ tool: 'Bash', tool_use_id: 'toolu_1', agentId: ID, command: ASSIGN.replace('assign-human', `assign-human --asker-agent ${ID} --asker-name Review-the-diff`) }])
    expect(result).toEqual({ result: { stdout: 'ok' } })
  })

  test('the type names it where the description is empty, and the id alone where it is not listed or the list fails', async () => {
    const typed = await harness({ agents: [{ id: ID, description: '', type: 'Explore' }] }).call({ tool: 'Bash', agentId: ID, command: ASSIGN })
    expect(typed.ran[0]!.command).toContain(`--asker-agent ${ID} --asker-name Explore --class`)
    for (const agents of [[], new Error('no list')]) {
      const { ran } = await harness({ agents }).call({ tool: 'Bash', agentId: ID, command: ASSIGN })
      expect(ran[0]!.command).toContain(`--asker-agent ${ID} --class`)
    }
  })

  test('the main loop, another command, an id that fails the pattern, and an internal fork change nothing and read no list', async () => {
    const cases: [Record<string, unknown>, Record<string, string>?][] = [
      [{ tool: 'Bash', command: ASSIGN }],
      [{ tool: 'Bash', agentId: ID, command: 'ls -la' }],
      [{ tool: 'Bash', agentId: 'a b', command: ASSIGN }],
      [{ tool: 'Bash', agentId: ID }],
      [{ tool: 'Bash', agentId: ID, command: ASSIGN }, { SMNS_INTERNAL: '1' }],
    ]
    for (const [e, env] of cases) {
      const h = harness({ agents: [{ id: ID, description: 'x', type: 'y' }], ...(env !== undefined && { env }) })
      const { ran } = await h.call(e)
      expect(ran).toEqual([e])
      expect(h.listed()).toBe(0)
    }
  })

  test("a teammate's id is attributed", async () => {
    const { ran } = await harness().call({ tool: 'Bash', agentId: 'fixer@team-1', command: 'sminos task assign --class needed --title T' })
    expect(ran[0]!.command).toBe('sminos task assign --asker-agent fixer@team-1 --class needed --title T')
  })

  test("the hook's failure passes the call on unchanged", async () => {
    const h = harness()
    const e = { tool: 'Bash', agentId: ID, command: ASSIGN }
    const ran: Record<string, unknown>[] = []
    const out = await h.hooks[0]!.caught!(h.$, e, async (passed) => {
      ran.push(passed)
      return { result: 'ran' }
    })
    expect(ran).toEqual([e])
    expect(out).toEqual({ result: 'ran' })
  })
})
