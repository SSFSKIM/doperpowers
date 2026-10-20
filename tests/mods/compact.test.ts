import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On, SessionCompactTrigger } from 'claude-code'

import {
  COMPACT,
  OFFER_GATE,
  RESUME_DEFAULT,
  compactStart,
  compactTurnComplete,
  compactTurnStart,
  compactedOfferText,
  describeCompact,
  isOfferText,
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
    expect(offerDue(280_000, 0, OFFER_GATE)).toBe(false)
    expect(offerDue(300_000, 0, OFFER_GATE)).toBe(true)
    expect(offerDue(undefined, 0, OFFER_GATE)).toBe(false)
  })

  test('after an offer, the next waits for a step of growth', async () => {
    expect(offerDue(382_000, 312_400, OFFER_GATE)).toBe(false)
    expect(offerDue(382_400, 312_400, OFFER_GATE)).toBe(true)
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
    expect(gated).toContain("at the end of each turn from 300,000 tokens on, once it has grown 70,000 since the last time (a message from the doperpowers plugin")
    expect(gated).toContain('Until the first time, you are under 300,000.')
    expect(gated).toContain('compact unasked at any checkpoint, mid-turn included')
    expect(gated).not.toContain('context_usage')
    const every = describeCompact(967_000, { floor: 0, step: 0 })
    expect(every).toContain("at the end of every turn (a message from the doperpowers plugin")
    expect(every).not.toContain('Until the first time')
    expect(describeCompact(967_000, { floor: 200_000, step: 0 })).toContain("at the end of each turn from 200,000 tokens on (a message from the doperpowers plugin")
    expect(describeCompact(967_000, { floor: 0, step: 50_000 })).toContain("at the end of each turn, once it has grown 50,000 since the last time (a message from the doperpowers plugin")
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
    expect(text).toContain('If you truly think this is the right time to compact, you can compact now with\nmcp__doperpowers__compact (alone, then end your turn')
    expect(text).toContain('reply "Not compacting."')
  })

  test('below 300k the offer says compacting is not necessarily recommended', async () => {
    const early = offerText({ tokens: 240_000, window: 1_000_000 }, 967_000)
    expect(early).toContain('Below 300,000 tokens, compacting is not necessarily recommended unless this is a\nclean checkpoint')
    expect(early).toContain("needs the prior context's information and nuance as a whole.\nIf you truly think")
    expect(offerText({ tokens: 300_000, window: 1_000_000 }, 967_000)).not.toContain('not necessarily recommended')
  })

  test('an offer is known by its text, early or not, and a resume prompt is not one', async () => {
    expect(isOfferText(offerText({ tokens: 412_300, window: 1_000_000 }, 967_000))).toBe(true)
    expect(isOfferText(offerText({ tokens: 12_000, window: 200_000 }, 167_000))).toBe(true)
    expect(isOfferText(offerText({ window: 1_000_000 }, 967_000))).toBe(true)
    expect(isOfferText(RESUME_DEFAULT)).toBe(false)
    expect(isOfferText('Context: what we were doing. Pick up milestone 3.')).toBe(false)
  })

  test('the offer after a compaction says there is nothing to decide and asks for the decline line', async () => {
    const text = compactedOfferText()
    expect(text).toContain('compacted since this offer was made, so there is nothing to decide now')
    expect(text).toContain('Reply "Not compacting." (one line) and end your turn.')
    expect(text).not.toMatch(/\d/)
  })

  test('the scheduled text tells the model to end its turn and what comes next', async () => {
    const text = scheduledText({ resume: 'Pick up milestone 3.' })
    expect(text).toContain('End your turn now')
    expect(text).toContain('"Pick up milestone 3."')
  })
})


type Handler = (...args: unknown[]) => unknown
type Matcher = Record<string, unknown> | undefined
type Entered = { text: string } | { drop: string }

const start = (isInteractive: boolean) => ({ cwd: '/', surface: isInteractive ? ('terminal' as const) : null, isInteractive })
const turnEnd = (agentId?: string) => ({ ...(agentId !== undefined && { agentId }), turnId: 't', answer: '', durationMs: 1, isAborted: false, reason: 'answer' as const })
const compactAt = (trigger: SessionCompactTrigger = 'manual', agentId?: string) => ({ trigger, ...(agentId !== undefined && { agentId }), messages: [] })
const stopAt = (fields: Record<string, unknown> = {}) => ({ hook_event_name: 'Stop', session_id: 's', transcript_path: '/t', cwd: '/', stop_hook_active: false, ...fields })

/** A matcher as the engine reads one: a RegExp tests a string, an object is a partial at any depth, else `===`. */
function matches(matcher: unknown, value: unknown): boolean {
  if (matcher instanceof RegExp) {
    return typeof value === 'string' && matcher.test(value)
  }
  if (typeof matcher === 'object' && matcher !== null) {
    return typeof value === 'object' && value !== null && Object.entries(matcher).every(([k, v]) => matches(v, (value as Record<string, unknown>)[k]))
  }
  return matcher === value
}

/**
 * A registrar that keeps the matched hooks, and an engine of plain records:
 * what the hooks call is written down, and what they are told is set here.
 * The shares of the shared events are called as register.tsx calls them.
 * A prompt the mod submits waits, as the engine's does, until the test lets
 * it enter (through the mod's own prompt.submit hook, then its turn's start)
 * or settles it otherwise.
 */
function harness(
  options: { window?: number; compactionWindow?: number; tokens?: number; env?: Record<string, string>; compact?: () => Promise<unknown>; usage?: () => never } = {},
) {
  const hooks: { event: string; matcher: Matcher; handler: Handler; fallback?: Handler }[] = []
  const on = ((event: string, ...rest: unknown[]) => {
    const handler = rest[rest.length - 1] as Handler
    const matcher = rest.length > 1 ? (rest[0] as Matcher) : undefined
    const entry: (typeof hooks)[number] = { event, matcher, handler }
    hooks.push(entry)
    return { catch: (fallback: Handler) => void (entry.fallback = fallback) }
  }) as unknown as On
  const calls: { op: string; args: unknown }[] = []
  const record = (op: string) => (...args: unknown[]) => {
    calls.push({ op, args: args.length > 1 ? args : args[0] })
  }
  // The figure the next usage read answers; a test moves it between turns.
  // Undefined is the engine's answer until a response follows a compaction.
  const state: { tokens: number | undefined } = { tokens: options.tokens ?? 312_400 }
  // Prompts submitted and not yet settled, in the order they were queued.
  const queue: { text: string; settle: (entered: Entered) => void }[] = []
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
    prompt: {
      submit: (args: { text: string }) =>
        new Promise<Entered>((settle) => {
          calls.push({ op: 'prompt.submit', args })
          queue.push({ text: args.text, settle })
        }),
    },
    ui: { toast: record('ui.toast'), log: record('ui.log') },
  }
  resetCompact()
  registerCompact(on)
  const engine = $ as unknown as EngineInterface
  const mod = { start: compactStart, turnStart: compactTurnStart, turnComplete: compactTurnComplete }
  const find = (event: string, e: Record<string, unknown>) => {
    const hook = hooks.find((h) => h.event === event && matches(h.matcher ?? {}, e))
    if (hook === undefined) {
      throw new Error(`no ${event} hook for ${JSON.stringify(e)}`)
    }
    return hook
  }
  // Lets the detached submit settle: a few microtask turns, no timer.
  const settle = async () => {
    for (let i = 0; i < 8; i++) {
      await Promise.resolve()
    }
  }
  const call = (e: Record<string, unknown>) => find('tool.call', e).handler($, e, async () => ({}))
  // The Stop as the engine raises it, the settings hooks beneath answering `beneath`.
  const stop = (e: Record<string, unknown> = stopAt(), beneath: Record<string, unknown> = {}) =>
    find('classic.Stop', e).handler($, e, async () => beneath) as Promise<Record<string, unknown>>
  const begin = (agentId?: string) => {
    const e = { text: '', turnId: 't', ...(agentId !== undefined && { agentId }) }
    return find('turn.start', e).handler($, e, async () => ({ turnId: 't' }))
  }
  const end = async (e: Record<string, unknown> = turnEnd()) => {
    await find('turn.complete', e).handler($, e, async () => ({ text: '' }))
    await settle()
  }
  /** A main turn the model answers: its start, the context it ends at, its Stop, its end. */
  const turn = async (tokens?: number, beneath: Record<string, unknown> = {}) => {
    await begin()
    if (tokens !== undefined) {
      state.tokens = tokens
    }
    await stop(stopAt(), beneath)
    await end()
  }
  /**
   * The oldest prompt waiting enters, as the engine runs it once the session
   * is idle: through the mod's prompt.submit hook (a prompt of the plugin's;
   * the hook that submitted it is another), its turn starting before the
   * submission resolves. Answers the text the session received. `refused`
   * is a hook beneath (or a settings hook's block) dropping it: no turn.
   */
  const enter = async (refused?: string) => {
    const waiting = queue.shift()
    if (waiting === undefined) {
      throw new Error('no prompt waits to enter')
    }
    const e = { text: waiting.text, origin: { kind: 'plugin', name: 'doperpowers' }, wait: false }
    let received = waiting.text
    const entered = (await find('prompt.submit', e).handler($, e, async (down: { text: string }) => {
      received = down.text
      if (refused !== undefined) {
        return { drop: refused }
      }
      await begin()
      return { text: down.text, origin: e.origin }
    })) as Entered
    waiting.settle(entered)
    await settle()
    return received
  }
  /** The oldest prompt waiting settles without passing the mod's hook: the engine removed it from the queue, or a hook above answered it. */
  const settleWaiting = async (entered: Entered) => {
    queue.shift()?.settle(entered)
    await settle()
  }
  /** An offer enters, and its turn ends on the model's decline. */
  const decline = async () => {
    const received = await enter()
    await stop()
    await end()
    return received
  }
  const submitted = () => calls.filter((c) => c.op === 'prompt.submit').map((c) => (c.args as { text: string }).text)
  const offers = () => submitted().filter(isOfferText)
  const registered = () => calls.filter((c) => c.op === 'tool.register').map((c) => (c.args as { name: string }).name)
  const sessionCompact = (e: Record<string, unknown>, beneath: Record<string, unknown> = { messages: [], tokensBefore: 312_400, tokensAfter: 20_000 }) =>
    find('session.compact', e).handler($, e, async () => beneath) as Promise<Record<string, unknown>>
  return { calls, call, stop, begin, end, turn, enter, settleWaiting, decline, submitted, offers, sessionCompact, mod, engine, settle, registered, state, queue }
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
    await h.turn()
    expect(h.offers()[0]).toContain('312,400 tokens; window 900,000')
    expect(h.offers()[0]).toContain('about 867,000')
  })

  test("the turn's end submits the offer as the plugin's prompt, its text whole, and the Stop is left as the hooks beneath answered it", async () => {
    const h = harness({ tokens: 412_300 })
    await h.mod.start(h.engine, start(true))
    const beneath = { additionalContext: ['from a shell hook'] }
    await h.begin()
    expect(await h.stop(stopAt(), beneath)).toBe(beneath)
    expect(h.submitted()).toEqual([])
    await h.end()
    expect(h.submitted()).toEqual([offerText({ tokens: 412_300, window: 1_000_000 }, 967_000)])
  })

  test("the turn's end is offered a compaction from the floor on, once per step of growth", async () => {
    const h = harness({ tokens: 200_000 })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    expect(h.offers()).toEqual([])
    await h.turn(312_400)
    expect(h.offers()).toHaveLength(1)
    expect(h.offers()[0]).toContain('Context: 312,400 tokens')
    await h.decline()
    await h.turn(380_000)
    expect(h.offers()).toHaveLength(1)
    await h.turn(390_000)
    expect(h.offers()).toHaveLength(2)
    expect(h.offers()[1]).toContain('Context: 390,000 tokens')
  })

  test("the offer's own turn ends with no offer, so even a gate of zeros does not loop", async () => {
    const h = harness({ tokens: 12_000, env: { DOPERPOWERS_COMPACT_OFFER_FLOOR: '0', DOPERPOWERS_COMPACT_OFFER_STEP: '0' } })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    expect(h.offers()).toHaveLength(1)
    expect(await h.decline()).toBe(h.offers()[0])
    expect(h.submitted()).toHaveLength(1)
    // The next turn the person starts is not the offer's, and is offered again.
    await h.turn()
    expect(h.offers()).toHaveLength(2)
  })

  test('an offer the model takes in its own turn compacts at that turn\'s end, then the resume prompt enters', async () => {
    const h = harness({ tokens: OFFER_GATE.floor })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.enter()
    const answer = (await h.call({ tool: COMPACT, tool_use_id: 't1', instructions: 'keep the plan', resume: 'Resume M3.' })) as { result: string }
    expect(answer.result).toContain('End your turn now')
    await h.stop()
    await h.end()
    const ops = h.calls.filter((c) => c.op === 'session.compact' || c.op === 'prompt.submit').map((c) => c.op)
    expect(ops).toEqual(['prompt.submit', 'session.compact', 'prompt.submit'])
    expect(h.submitted()[1]).toBe('Resume M3.')
  })

  test('while an offer waits, a turn queued ahead of it ends with no second offer, and the offer enters with the figures it reads then', async () => {
    const h = harness({ tokens: 400_000 })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    expect(h.offers()[0]).toContain('Context: 400,000 tokens')
    // The person's prompt, queued during the turn, runs first, and grows
    // the context past a step: one offer waits already.
    await h.turn(480_000)
    expect(h.offers()).toHaveLength(1)
    const received = await h.enter()
    expect(received).toBe(offerText({ tokens: 480_000, window: 1_000_000 }, 967_000))
    await h.stop()
    await h.end()
    // The step is counted from the figure the offer carried when it entered.
    await h.turn(540_000)
    expect(h.offers()).toHaveLength(1)
    await h.turn(550_000)
    expect(h.offers()).toHaveLength(2)
  })

  test("another of the plugin's prompts passes the prompt.submit hook untouched, and its turn is no offer's", async () => {
    const h = harness({ tokens: 12_000, env: { DOPERPOWERS_COMPACT_OFFER_FLOOR: '0', DOPERPOWERS_COMPACT_OFFER_STEP: '0' } })
    await h.mod.start(h.engine, start(true))
    await h.call({ tool: COMPACT, tool_use_id: 't1', resume: 'Resume M3.' })
    await h.end()
    expect(h.offers()).toEqual([])
    expect(await h.enter()).toBe('Resume M3.')
    await h.stop()
    await h.end()
    expect(h.offers()).toHaveLength(1)
  })

  test('an offer the engine removes from the queue gives its step back', async () => {
    const h = harness({ tokens: 400_000 })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.settleWaiting({ drop: 'the prompt was removed from the queue before it ran' })
    expect(h.calls.some((c) => c.op === 'ui.log' && JSON.stringify(c.args).includes('removed from the queue'))).toBe(true)
    // Within a step of the offer that never ran: offered again.
    await h.turn(410_000)
    expect(h.offers()).toHaveLength(2)
    expect(h.offers()[1]).toContain('Context: 410,000 tokens')
    // Settled by a hook above this module's prompt.submit, never passing it: the same.
    await h.settleWaiting({ text: 'answered above' })
    await h.turn(420_000)
    expect(h.offers()).toHaveLength(3)
  })

  test('an offer a hook beneath refuses stays spent, so a hook that always refuses costs no submission every turn', async () => {
    const h = harness({ tokens: 400_000 })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.enter('blocked by a settings hook')
    await h.turn(410_000)
    expect(h.offers()).toHaveLength(1)
    await h.turn(470_000)
    expect(h.offers()).toHaveLength(2)
  })

  test('an offer removed after a compaction stood leaves the baseline the compaction started', async () => {
    const h = harness({ tokens: 400_000 })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.decline()
    await h.turn(480_000)
    await h.sessionCompact(compactAt())
    await h.settleWaiting({ drop: 'the prompt was removed from the queue before it ran' })
    // Not the 400,000 the removed offer replaced: 0, as the compaction left it.
    await h.turn(420_000)
    expect(h.offers()).toHaveLength(3)
  })

  test('an offer that enters after a compaction the person queued ahead of it says there is nothing to decide', async () => {
    const h = harness({ tokens: 480_000 })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    expect(h.offers()[0]).toContain('Context: 480,000 tokens')
    // A /compact queued during the turn runs first; no response follows it
    // before the offer enters, so the engine has no figure.
    await h.sessionCompact(compactAt('manual'))
    h.state.tokens = undefined
    expect(await h.enter()).toBe(compactedOfferText())
    await h.stop()
    await h.end()
    expect(h.offers()).toHaveLength(1)
    // The baseline is the compaction's, not the stale figure's.
    h.state.tokens = 30_000
    await h.turn()
    await h.turn(OFFER_GATE.floor)
    expect(h.offers()).toHaveLength(2)
  })

  test('an offer that enters after the model compacted in a turn queued ahead of it says there is nothing to decide', async () => {
    const h = harness({ tokens: 480_000 })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    // The person's queued turn, in which the model compacts.
    await h.begin()
    await h.call({ tool: COMPACT, tool_use_id: 't1', resume: 'Resume M3.' })
    await h.stop()
    await h.end()
    expect(h.calls.filter((c) => c.op === 'session.compact')).toHaveLength(1)
    // Even with a figure to read, the compaction since the submission decides.
    h.state.tokens = 25_000
    expect(await h.enter()).toBe(compactedOfferText())
    await h.stop()
    await h.end()
    expect(await h.enter()).toBe('Resume M3.')
  })

  test('an offer that enters with no figure to read says there is nothing to decide', async () => {
    const h = harness({ tokens: 480_000 })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    h.state.tokens = undefined
    expect(await h.enter()).toBe(compactedOfferText())
  })

  test("an offer's turn that ends interrupted leaves the next turn the person's", async () => {
    const h = harness({ tokens: 12_000, env: { DOPERPOWERS_COMPACT_OFFER_FLOOR: '0', DOPERPOWERS_COMPACT_OFFER_STEP: '0' } })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.enter()
    // Interrupted: its end is not an answered one, so no turn.complete of this mod's.
    await h.turn()
    expect(h.offers()).toHaveLength(2)
  })

  test('a request already pending needs no offer', async () => {
    const h = harness({ tokens: 500_000 })
    await h.mod.start(h.engine, start(true))
    await h.begin()
    await h.call({ tool: COMPACT, tool_use_id: 't1' })
    await h.stop()
    await h.end()
    expect(h.offers()).toEqual([])
    expect(h.submitted()).toEqual([RESUME_DEFAULT])
  })

  test("a subagent's turn end or Stop, or a session without the tool, is offered nothing", async () => {
    const withTool = harness({ tokens: 500_000 })
    await withTool.mod.start(withTool.engine, start(true))
    await withTool.stop(stopAt({ agent_id: 'a1' }), { preventContinuation: true })
    await withTool.end(turnEnd('a1'))
    expect(withTool.submitted()).toEqual([])
    // The subagent's Stop prevented nothing of the main turn's.
    await withTool.turn()
    expect(withTool.offers()).toHaveLength(1)
    const headless = harness({ tokens: 500_000 })
    await headless.turn()
    expect(headless.submitted()).toEqual([])
  })

  test('a below-floor turn end resets the baseline after a compaction', async () => {
    const h = harness({ tokens: 312_400 })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.decline()
    await h.turn(60_000)
    expect(h.offers()).toHaveLength(1)
    await h.turn(320_000)
    expect(h.offers()).toHaveLength(2)
    expect(h.offers()[1]).toContain('Context: 320,000 tokens')
  })

  test('a turn end below the last offer resets the baseline even above the floor', async () => {
    const h = harness({ tokens: 500_000 })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.decline()
    await h.turn(320_000)
    expect(h.offers()[1]).toContain('Context: 320,000 tokens')
  })

  test('a main-conversation compaction resets the offer baseline once it stands', async () => {
    for (const trigger of ['manual', 'auto', 'plugin'] as const) {
      const h = harness({ tokens: OFFER_GATE.floor })
      await h.mod.start(h.engine, start(true))
      await h.turn()
      await h.decline()
      const beneath = { messages: [], tokensBefore: OFFER_GATE.floor, tokensAfter: 20_000 }
      expect(await h.sessionCompact(compactAt(trigger), beneath)).toBe(beneath)
      // No turn end saw the shrink: equal figures cannot reset the baseline.
      await h.turn()
      expect(h.offers()).toHaveLength(2)
    }
  })

  test('a skipped compaction leaves the offer baseline intact', async () => {
    const h = harness({ tokens: OFFER_GATE.floor })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.decline()
    const beneath = { skip: 'blocked by a hook' }
    expect(await h.sessionCompact(compactAt(), beneath)).toBe(beneath)
    await h.turn()
    expect(h.offers()).toHaveLength(1)
  })

  test("a subagent's compaction leaves the offer baseline intact", async () => {
    const h = harness({ tokens: OFFER_GATE.floor })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.decline()
    await h.sessionCompact(compactAt('auto', 'a1'))
    await h.turn()
    expect(h.offers()).toHaveLength(1)
  })

  test('a precompute leaves the offer baseline intact', async () => {
    const h = harness({ tokens: OFFER_GATE.floor })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.decline()
    await h.sessionCompact(compactAt('precompute'))
    await h.turn()
    expect(h.offers()).toHaveLength(1)
  })

  test('the environment overrides the gate, a figure at a time, and a bad one is ignored', async () => {
    const every = harness({ tokens: 12_000, env: { DOPERPOWERS_COMPACT_OFFER_FLOOR: '0', DOPERPOWERS_COMPACT_OFFER_STEP: '0' } })
    await every.mod.start(every.engine, start(true))
    await every.turn()
    await every.decline()
    await every.turn()
    expect(every.offers()).toHaveLength(2)
    expect(every.offers()[1]).toContain('Context: 12,000 tokens')
    const spec = every.calls.find((c) => c.op === 'tool.register')?.args as { description: string }
    expect(spec.description).toContain('at the end of every turn')

    const bad = harness({ tokens: 200_000, env: { DOPERPOWERS_COMPACT_OFFER_FLOOR: 'abc', DOPERPOWERS_COMPACT_OFFER_STEP: '-1' } })
    await bad.mod.start(bad.engine, start(true))
    await bad.turn()
    expect(bad.offers()).toEqual([])
  })

  test('a figure that cannot be read offers nothing, logged', async () => {
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
    await h.turn()
    expect(h.submitted()).toEqual([])
    expect(h.calls.some((c) => c.op === 'ui.log' && JSON.stringify(c.args).includes('no session'))).toBe(true)
  })

  test("an offer whose figures cannot be read again enters as it was written", async () => {
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
    await h.turn()
    fail = true
    expect(await h.enter()).toBe(h.offers()[0])
  })

  test('a hook preventing continuation withholds the offer without spending it', async () => {
    const h = harness({ tokens: OFFER_GATE.floor })
    await h.mod.start(h.engine, start(true))
    const beneath = { additionalContext: ['from a shell hook'], preventContinuation: true }
    await h.begin()
    expect(await h.stop(stopAt(), beneath)).toBe(beneath)
    await h.end()
    expect(h.submitted()).toEqual([])
    await h.turn()
    expect(h.offers()).toHaveLength(1)
  })

  test('a compact call is answered at once and compacted when the main turn ends, then the resume prompt enters', async () => {
    const h = harness({ tokens: OFFER_GATE.floor })
    await h.mod.start(h.engine, start(true))
    await h.turn()
    await h.decline()
    await h.begin()
    const answer = (await h.call({ tool: COMPACT, tool_use_id: 't1', instructions: 'keep the plan', resume: 'Resume M3.' })) as { result: string }
    expect(answer.result).toContain('End your turn now')
    expect(h.calls.some((c) => c.op === 'session.compact')).toBe(false)

    // A subagent's turn end in between is not the main conversation's.
    await h.end(turnEnd('a1'))
    expect(h.calls.some((c) => c.op === 'session.compact')).toBe(false)

    await h.stop()
    await h.end()
    const ops = h.calls.filter((c) => c.op === 'session.compact' || c.op === 'prompt.submit').slice(1)
    expect(ops).toEqual([
      { op: 'session.compact', args: { instructions: 'keep the plan' } },
      { op: 'prompt.submit', args: { text: 'Resume M3.' } },
    ])
    expect(await h.enter()).toBe('Resume M3.')

    // This plugin's compaction passes no hook of its own, so it resets the
    // baseline itself, even when no turn end observes the shrink.
    await h.stop()
    await h.end()
    expect(h.offers()).toHaveLength(2)

    // The request is spent: no turn end compacts again.
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
    expect(skipped.submitted()).toEqual([RESUME_DEFAULT])

    const failed = harness({
      compact: async () => {
        throw new Error('a turn is running')
      },
    })
    await failed.call({ tool: COMPACT, tool_use_id: 't1' })
    await failed.mod.turnComplete(failed.engine, turnEnd())
    await failed.settle()
    expect(failed.calls.some((c) => c.op === 'ui.toast' && String(c.args).includes('a turn is running'))).toBe(true)
    expect(failed.submitted()).toEqual([RESUME_DEFAULT])
  })
})
