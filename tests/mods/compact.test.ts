import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import {
  COMPACT,
  OFFER_GATE,
  RESUME_DEFAULT,
  compactStart,
  compactStop,
  compactTurnComplete,
  compactTurnStart,
  describeCompact,
  offerDue,
  offerText,
  readRequest,
  registerCompact,
  resetCompact,
  scheduledText,
  thresholdOf,
  usageText,
} from '../../hooks/mods/compact'

tier('user')

describe('thresholdOf', () => {
  test('is the window less the output reserve and the headroom', async () => {
    expect(thresholdOf(1_000_000)).toBe(967_000)
    expect(thresholdOf(200_000)).toBe(167_000)
  })

  test('never goes below zero', async () => {
    expect(thresholdOf(10_000)).toBe(0)
  })
})

describe('offerDue', () => {
  test('nothing under the floor, the first offer at the floor', async () => {
    expect(offerDue(250_000, 0, OFFER_GATE)).toBe(false)
    expect(offerDue(300_000, 0, OFFER_GATE)).toBe(true)
    expect(offerDue(undefined, 0, OFFER_GATE)).toBe(false)
  })

  test('after an offer, the next waits for a step of growth', async () => {
    expect(offerDue(340_000, 312_400, OFFER_GATE)).toBe(false)
    expect(offerDue(362_400, 312_400, OFFER_GATE)).toBe(true)
  })

  test('a figure below the last offer is a compaction since, and growth counts from the reset', async () => {
    expect(offerDue(60_000, 500_000, OFFER_GATE)).toBe(false)
    expect(offerDue(320_000, 500_000, OFFER_GATE)).toBe(true)
  })

  test('a gate of zeros offers at every turn', async () => {
    expect(offerDue(12_000, 0, { floor: 0, step: 0 })).toBe(true)
    expect(offerDue(12_000, 12_000, { floor: 0, step: 0 })).toBe(true)
  })
})

describe('readRequest', () => {
  test('trims both strings and defaults the resume line', async () => {
    expect(readRequest({ instructions: '  keep the ids ', resume: ' go on ' })).toEqual({ instructions: 'keep the ids', resume: 'go on' })
    expect(readRequest({})).toEqual({ resume: RESUME_DEFAULT })
  })

  test('reads anything but a non-empty string as absent', async () => {
    expect(readRequest({ instructions: 7, resume: '' })).toEqual({ resume: RESUME_DEFAULT })
    expect(readRequest({ instructions: '   ', resume: ['x'] })).toEqual({ resume: RESUME_DEFAULT })
  })
})

describe('texts', () => {
  test('the compact description names the harness threshold, or its absence', async () => {
    expect(describeCompact(967_000)).toContain('compacts on its own at about 967,000')
    expect(describeCompact(undefined)).toContain("compacts on its own near the window's end")
    expect(describeCompact(967_000)).toContain('Runs when\nthis turn ends')
    expect(describeCompact(967_000)).toContain('300k–450k: at any reasonable checkpoint')
    expect(describeCompact(967_000)).toContain('Prefer not to pass 600k')
    expect(describeCompact(967_000)).toContain('a backstop, not the plan')
    expect(describeCompact(967_000)).toContain('never as a percentage of the window')
    expect(describeCompact(967_000)).toContain('Not during a design discussion, at any size')
  })

  test('the compact description tells the model when it is told its size, by the gate', async () => {
    const gated = describeCompact(967_000)
    expect(gated).toContain("at the end of each turn from 300,000 tokens on, once it has grown 50,000 since the last time (a Stop hook's additional context")
    expect(gated).toContain('Until the first time, you are under 300,000.')
    expect(gated).toContain('compact unasked at any checkpoint, mid-turn included')
    expect(gated).not.toContain('context_usage')
    const every = describeCompact(967_000, { floor: 0, step: 0 })
    expect(every).toContain("at the end of every turn (a Stop hook's additional context")
    expect(every).not.toContain('Until the first time')
    expect(describeCompact(967_000, { floor: 200_000, step: 0 })).toContain("at the end of each turn from 200,000 tokens on (a Stop hook's additional context")
    expect(describeCompact(967_000, { floor: 0, step: 50_000 })).toContain("at the end of each turn, once it has grown 50,000 since the last time (a Stop hook's additional context")
  })

  test('the usage text carries the figures and the threshold', async () => {
    expect(usageText({ tokens: 312_400, window: 1_000_000 }, 967_000)).toBe(
      'Context: 312,400 tokens; window 1,000,000. The harness compacts on its own at about 967,000 tokens.',
    )
    expect(usageText({ tokens: 50_000, window: 200_000 }, 167_000)).not.toContain('%')
    expect(usageText({ window: 1_000_000 }, 967_000)).toContain('no model response yet')
  })

  test('the offer carries the figures, names the tool, and asks for a line on a decline', async () => {
    const text = offerText({ tokens: 412_300, window: 1_000_000 }, 967_000)
    expect(text).toContain('Context: 412,300 tokens; window 1,000,000.')
    expect(text).toContain('call mcp__doperpowers__compact, alone, then end your turn')
    expect(text).toContain('reply "Not compacting."')
  })

  test('the scheduled text tells the model to end its turn and what comes next', async () => {
    const text = scheduledText({ resume: 'Pick up milestone 3.' })
    expect(text).toContain('End your turn now')
    expect(text).toContain('"Pick up milestone 3."')
  })
})

type Handler = (...args: unknown[]) => unknown
type Matcher = Record<string, unknown> | undefined

const start = (isInteractive: boolean) => ({ cwd: '/', surface: isInteractive ? ('terminal' as const) : null, isInteractive })
const turnEnd = (agentId?: string) => ({ ...(agentId !== undefined && { agentId }), turnId: 't', answer: '', durationMs: 1, isAborted: false, reason: 'answer' as const })
const stopAt = (fields: Record<string, unknown> = {}) => ({ hook_event_name: 'Stop', session_id: 's', transcript_path: '/t', cwd: '/', stop_hook_active: false, ...fields })

/**
 * A registrar that keeps the matched hooks, and an engine of plain records:
 * what the hooks call is written down, and what they are told is set here.
 * The shares of the shared events are called as register.tsx calls them.
 */
function harness(
  options: { window?: number; compactionWindow?: number; tokens?: number; env?: Record<string, string>; compact?: () => Promise<unknown>; usage?: () => never } = {},
) {
  const hooks: { event: string; matcher: Matcher; handler: Handler }[] = []
  const on = ((event: string, ...rest: unknown[]) => {
    const handler = rest[rest.length - 1] as Handler
    const matcher = rest.length > 1 ? (rest[0] as Matcher) : undefined
    hooks.push({ event, matcher, handler })
  }) as unknown as On
  const calls: { op: string; args: unknown }[] = []
  const record = (op: string) => (args?: unknown) => {
    calls.push({ op, args })
  }
  // The figure the next usage read answers; a test moves it between turns.
  const state = { tokens: options.tokens ?? 312_400 }
  const $ = {
    session: {
      // The breakdown, asked for, measures against the compaction window.
      usage: async (args?: { breakdown?: string }) => {
        options.usage?.()
        return {
          context: {
            tokens: state.tokens,
            window: options.window ?? 1_000_000,
            percent: 31,
            ...(args?.breakdown !== undefined &&
              options.compactionWindow !== undefined && { breakdown: { rawMaxTokens: options.compactionWindow, maxTokens: options.compactionWindow } }),
          },
          rateLimits: [],
        }
      },
      compact: async (args: unknown) => {
        calls.push({ op: 'session.compact', args })
        return options.compact === undefined ? { messages: [], tokensBefore: 312_400, tokensAfter: 20_000 } : options.compact()
      },
    },
    env: { get: async (name: string) => options.env?.[name] },
    tool: { register: async (spec: { name: string }) => (calls.push({ op: 'tool.register', args: spec }), { tool: `mcp__doperpowers__${spec.name}` }) },
    prompt: { submit: async (args: unknown) => (calls.push({ op: 'prompt.submit', args }), { text: (args as { text: string }).text }) },
    ui: { toast: record('ui.toast'), log: record('ui.log') },
  }
  resetCompact()
  registerCompact(on)
  const engine = $ as unknown as EngineInterface
  const mod = { start: compactStart, stop: compactStop, turnStart: compactTurnStart, turnComplete: compactTurnComplete }
  const find = (event: string, e: Record<string, unknown>) => {
    const hook = hooks.find((h) => h.event === event && Object.entries(h.matcher ?? {}).every(([k, v]) => e[k] === v))
    if (hook === undefined) {
      throw new Error(`no ${event} hook for ${JSON.stringify(e)}`)
    }
    return hook
  }
  const call = (e: Record<string, unknown>) => find('tool.call', e).handler($, e, async () => ({}))
  // The Stop as the engine raises it, the settings hooks beneath answering `beneath`.
  const stop = (e: Record<string, unknown>, beneath: Record<string, unknown> = {}) =>
    find('classic.Stop', e).handler($, e, async () => beneath) as Promise<{ additionalContext?: string[] }>
  // Lets the detached submit settle: a few microtask turns, no timer.
  const settle = async () => {
    for (let i = 0; i < 8; i++) {
      await Promise.resolve()
    }
  }
  const registered = () => calls.filter((c) => c.op === 'tool.register').map((c) => (c.args as { name: string }).name)
  return { calls, call, stop, mod, engine, settle, registered, state }
}

describe('registerCompact', () => {
  test('registers the compact tool alone at session start', async () => {
    const h = harness()
    await h.mod.start(h.engine, start(true))
    expect(h.registered()).toEqual(['compact'])
    const spec = h.calls.find((c) => c.op === 'tool.register' && (c.args as { name: string }).name === 'compact')?.args as { description: string }
    expect(spec.description).toContain('at about 967,000')
    expect(spec.description).toContain('from 300,000 tokens on')
  })

  test('a compaction window smaller than the model window is the one measured against', async () => {
    const h = harness({ window: 1_000_000, compactionWindow: 900_000 })
    await h.mod.start(h.engine, start(true))
    const spec = h.calls.find((c) => c.op === 'tool.register' && (c.args as { name: string }).name === 'compact')?.args as { description: string }
    expect(spec.description).toContain('at about 867,000')
    const offered = await h.stop(stopAt())
    expect(offered.additionalContext?.[0]).toContain('312,400 tokens; window 900,000')
    expect(offered.additionalContext?.[0]).toContain('about 867,000')
  })

  test("the turn's end is offered a compaction from the floor on, once per step of growth", async () => {
    const h = harness({ tokens: 250_000 })
    await h.mod.start(h.engine, start(true))
    expect((await h.stop(stopAt())).additionalContext).toBeUndefined()
    h.state.tokens = 312_400
    expect((await h.stop(stopAt())).additionalContext?.[0]).toContain('Context: 312,400 tokens')
    h.state.tokens = 340_000
    expect((await h.stop(stopAt())).additionalContext).toBeUndefined()
    h.state.tokens = 365_000
    expect((await h.stop(stopAt())).additionalContext?.[0]).toContain('Context: 365,000 tokens')
  })

  test('the Stop after the offered step passes, so the offer is one step', async () => {
    const h = harness({ tokens: 500_000 })
    await h.mod.start(h.engine, start(true))
    expect((await h.stop(stopAt({ stop_hook_active: true }))).additionalContext).toBeUndefined()
    expect((await h.stop(stopAt())).additionalContext).toHaveLength(1)
  })

  test('a request already pending needs no offer', async () => {
    const h = harness({ tokens: 500_000 })
    await h.mod.start(h.engine, start(true))
    await h.call({ tool: COMPACT, tool_use_id: 't1' })
    expect((await h.stop(stopAt())).additionalContext).toBeUndefined()
  })

  test("a subagent's Stop, or a session without the tool, is offered nothing", async () => {
    const withTool = harness({ tokens: 500_000 })
    await withTool.mod.start(withTool.engine, start(true))
    expect((await withTool.stop(stopAt({ agent_id: 'a1' }))).additionalContext).toBeUndefined()
    const headless = harness({ tokens: 500_000 })
    expect((await headless.stop(stopAt())).additionalContext).toBeUndefined()
  })

  test('after a compaction, the growth counts from the reset', async () => {
    const h = harness({ tokens: 500_000 })
    await h.mod.start(h.engine, start(true))
    expect((await h.stop(stopAt())).additionalContext).toHaveLength(1)
    h.state.tokens = 60_000
    expect((await h.stop(stopAt())).additionalContext).toBeUndefined()
    h.state.tokens = 320_000
    expect((await h.stop(stopAt())).additionalContext?.[0]).toContain('Context: 320,000 tokens')
  })

  test('the environment overrides the gate, a figure at a time, and a bad one is ignored', async () => {
    const every = harness({ tokens: 12_000, env: { DOPERPOWERS_COMPACT_OFFER_FLOOR: '0', DOPERPOWERS_COMPACT_OFFER_STEP: '0' } })
    await every.mod.start(every.engine, start(true))
    expect((await every.stop(stopAt())).additionalContext?.[0]).toContain('Context: 12,000 tokens')
    expect((await every.stop(stopAt())).additionalContext?.[0]).toContain('Context: 12,000 tokens')
    const spec = every.calls.find((c) => c.op === 'tool.register')?.args as { description: string }
    expect(spec.description).toContain('at the end of every turn')

    const bad = harness({ tokens: 250_000, env: { DOPERPOWERS_COMPACT_OFFER_FLOOR: 'abc', DOPERPOWERS_COMPACT_OFFER_STEP: '-1' } })
    await bad.mod.start(bad.engine, start(true))
    expect((await bad.stop(stopAt())).additionalContext).toBeUndefined()
  })

  test("a figure that cannot be read passes the Stop, logged", async () => {
    let fail = false
    const h = harness({
      tokens: 500_000,
      usage: () => {
        if (fail) {
          throw new Error('no session')
        }
        return undefined as never
      },
    })
    await h.mod.start(h.engine, start(true))
    fail = true
    expect((await h.stop(stopAt())).additionalContext).toBeUndefined()
    expect(h.calls.some((c) => c.op === 'ui.log' && String(c.args).includes('no session'))).toBe(true)
  })

  test("the settings hooks' answer stands beside the offer", async () => {
    const h = harness({ tokens: 500_000 })
    await h.mod.start(h.engine, start(true))
    const answered = await h.stop(stopAt(), { additionalContext: ['from a shell hook'], preventContinuation: true })
    expect(answered.additionalContext?.length).toBe(2)
    expect(answered.additionalContext?.[0]).toBe('from a shell hook')
    expect(answered.additionalContext?.[1]).toContain('Context: 500,000 tokens')
    expect((answered as { preventContinuation?: true }).preventContinuation).toBe(true)
  })

  test('a compact call is answered at once and compacted when the main turn ends, then the resume prompt enters', async () => {
    const h = harness()
    await h.mod.start(h.engine, start(true))
    const answer = (await h.call({ tool: COMPACT, tool_use_id: 't1', instructions: 'keep the plan', resume: 'Resume M3.' })) as { result: string }
    expect(answer.result).toContain('End your turn now')
    expect(h.calls.some((c) => c.op === 'session.compact')).toBe(false)

    // A subagent's turn end in between is not the main conversation's.
    await h.mod.turnComplete(h.engine, turnEnd('a1'))
    expect(h.calls.some((c) => c.op === 'session.compact')).toBe(false)

    await h.mod.turnComplete(h.engine, turnEnd())
    await h.settle()
    const ops = h.calls.filter((c) => c.op === 'session.compact' || c.op === 'prompt.submit')
    expect(ops).toEqual([
      { op: 'session.compact', args: { instructions: 'keep the plan' } },
      { op: 'prompt.submit', args: { text: 'Resume M3.' } },
    ])

    // The request is spent: the next turn end compacts nothing.
    await h.mod.turnComplete(h.engine, turnEnd())
    expect(h.calls.filter((c) => c.op === 'session.compact').length).toBe(1)
  })

  test('a request left by a turn that did not end in an answer is dropped when the next turn starts', async () => {
    const h = harness()
    await h.call({ tool: COMPACT, tool_use_id: 't1' })
    h.mod.turnStart({})
    await h.mod.turnComplete(h.engine, turnEnd())
    await h.settle()
    expect(h.calls.some((c) => c.op === 'session.compact' || c.op === 'prompt.submit')).toBe(false)
  })

  test("a subagent's turn starting before the main turn ends keeps the request", async () => {
    const h = harness()
    await h.call({ tool: COMPACT, tool_use_id: 't1' })
    h.mod.turnStart({ agentId: 'a1' })
    await h.mod.turnComplete(h.engine, turnEnd())
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'session.compact').length).toBe(1)
  })

  test('a call from a subagent is refused', async () => {
    const h = harness()
    const answer = (await h.call({ tool: COMPACT, tool_use_id: 't1', agentId: 'a1' })) as { deny?: string }
    expect(answer.deny).toContain('main conversation')
    await h.mod.turnComplete(h.engine, turnEnd())
    expect(h.calls.some((c) => c.op === 'session.compact')).toBe(false)
  })

  test('the resume prompt enters even when the compaction is skipped or fails', async () => {
    const skipped = harness({ compact: async () => ({ skip: 'blocked by a hook' }) })
    await skipped.call({ tool: COMPACT, tool_use_id: 't1' })
    await skipped.mod.turnComplete(skipped.engine, turnEnd())
    await skipped.settle()
    expect(skipped.calls.some((c) => c.op === 'ui.toast' && String(c.args).includes('blocked by a hook'))).toBe(true)
    expect(skipped.calls.some((c) => c.op === 'prompt.submit' && (c.args as { text: string }).text === RESUME_DEFAULT)).toBe(true)

    const failed = harness({
      compact: async () => {
        throw new Error('a turn is running')
      },
    })
    await failed.call({ tool: COMPACT, tool_use_id: 't1' })
    await failed.mod.turnComplete(failed.engine, turnEnd())
    await failed.settle()
    expect(failed.calls.some((c) => c.op === 'ui.toast' && String(c.args).includes('a turn is running'))).toBe(true)
    expect(failed.calls.some((c) => c.op === 'prompt.submit')).toBe(true)
  })
})
