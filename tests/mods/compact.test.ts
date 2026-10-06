import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import {
  COMPACT,
  CONTEXT_USAGE,
  RESUME_DEFAULT,
  compactStart,
  compactTurnComplete,
  compactTurnStart,
  describeCompact,
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
    expect(describeCompact(967_000)).toContain('compacted when this turn ends')
  })

  test('the usage text carries the figures and the threshold', async () => {
    expect(usageText({ tokens: 312_400, window: 1_000_000 }, 967_000)).toBe(
      'Context: 312,400 of 1,000,000 tokens (31%). The harness compacts on its own at about 967,000 tokens.',
    )
    expect(usageText({ tokens: 50_000, window: 200_000 }, 167_000)).toContain('(25%)')
    expect(usageText({ window: 1_000_000 }, 967_000)).toContain('no model response yet')
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

/**
 * A registrar that keeps the matched hooks, and an engine of plain records:
 * what the hooks call is written down, and what they are told is set here.
 * The shares of the shared events are called as register.tsx calls them.
 */
function harness(options: { window?: number; compactionWindow?: number; compact?: () => Promise<unknown> } = {}) {
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
  const $ = {
    session: {
      // The breakdown, asked for, measures against the compaction window.
      usage: async (args?: { breakdown?: string }) => ({
        context: {
          tokens: 312_400,
          window: options.window ?? 1_000_000,
          percent: 31,
          ...(args?.breakdown !== undefined &&
            options.compactionWindow !== undefined && { breakdown: { rawMaxTokens: options.compactionWindow, maxTokens: options.compactionWindow } }),
        },
        rateLimits: [],
      }),
      compact: async (args: unknown) => {
        calls.push({ op: 'session.compact', args })
        return options.compact === undefined ? { messages: [], tokensBefore: 312_400, tokensAfter: 20_000 } : options.compact()
      },
    },
    tool: { register: async (spec: { name: string }) => (calls.push({ op: 'tool.register', args: spec }), { tool: `mcp__doperpowers__${spec.name}` }) },
    prompt: { submit: async (args: unknown) => (calls.push({ op: 'prompt.submit', args }), { text: (args as { text: string }).text }) },
    ui: { toast: record('ui.toast'), log: record('ui.log') },
  }
  resetCompact()
  registerCompact(on)
  const engine = $ as unknown as EngineInterface
  const mod = { start: compactStart, turnStart: compactTurnStart, turnComplete: compactTurnComplete }
  const call = (e: Record<string, unknown>) => {
    const hook = hooks.find((h) => h.event === 'tool.call' && Object.entries(h.matcher ?? {}).every(([k, v]) => e[k] === v))
    if (hook === undefined) {
      throw new Error(`no tool.call hook for ${String(e.tool)}`)
    }
    return hook.handler($, e, async () => ({}))
  }
  // Lets the detached submit settle: a few microtask turns, no timer.
  const settle = async () => {
    for (let i = 0; i < 8; i++) {
      await Promise.resolve()
    }
  }
  const registered = () => calls.filter((c) => c.op === 'tool.register').map((c) => (c.args as { name: string }).name)
  return { calls, call, mod, engine, settle, registered }
}

describe('registerCompact', () => {
  test('registers both tools at session start', async () => {
    const h = harness()
    await h.mod.start(h.engine, start(true))
    expect(h.registered()).toEqual(['context_usage', 'compact'])
    const spec = h.calls.find((c) => c.op === 'tool.register' && (c.args as { name: string }).name === 'compact')?.args as { description: string }
    expect(spec.description).toContain('at about 967,000')
  })

  test('context_usage answers the figures with the threshold of the session window', async () => {
    const h = harness({ window: 200_000 })
    await h.mod.start(h.engine, start(true))
    const answer = (await h.call({ tool: CONTEXT_USAGE, tool_use_id: 't1' })) as { result: string }
    expect(answer.result).toContain('312,400 of 200,000')
    expect(answer.result).toContain('about 167,000')
  })

  test('a compaction window smaller than the model window is the one measured against', async () => {
    const h = harness({ window: 1_000_000, compactionWindow: 900_000 })
    await h.mod.start(h.engine, start(true))
    const spec = h.calls.find((c) => c.op === 'tool.register' && (c.args as { name: string }).name === 'compact')?.args as { description: string }
    expect(spec.description).toContain('at about 867,000')
    const answer = (await h.call({ tool: CONTEXT_USAGE, tool_use_id: 't1' })) as { result: string }
    expect(answer.result).toContain('312,400 of 900,000 tokens (35%)')
    expect(answer.result).toContain('about 867,000')
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
    h.mod.turnStart()
    await h.mod.turnComplete(h.engine, turnEnd())
    await h.settle()
    expect(h.calls.some((c) => c.op === 'session.compact' || c.op === 'prompt.submit')).toBe(false)
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
