import type { EngineInterface, On, SessionStartInput, TurnCompleteInput } from 'claude-code'

/**
 * The tools as the model names them, `mcp__<plugin>__<name>` with the
 * plugin's manifest name; written out so the engine's scan reads the
 * matchers (the hooks below name them as literals for the same reason).
 */
export const COMPACT = 'mcp__doperpowers__compact'
export const CONTEXT_USAGE = 'mcp__doperpowers__context_usage'

/**
 * What the engine subtracts from the compaction window before compacting on
 * its own: the output reserve (at most 20k) and the headroom below it (13k).
 * On a 1M window the threshold is 967k, on 900k 867k, on 200k 167k.
 */
const OUTPUT_RESERVE = 20_000
const HEADROOM = 13_000

export function thresholdOf(window: number): number {
  return Math.max(0, window - OUTPUT_RESERVE - HEADROOM)
}

export const RESUME_DEFAULT = 'Continue from the summary.'

export type CompactRequest = {
  instructions?: string
  resume: string
}

/**
 * Reads the call's arguments: `instructions` and `resume`, strings, trimmed;
 * anything else is absent, and an absent `resume` is the default line.
 */
export function readRequest(args: Record<string, unknown>): CompactRequest {
  const text = (value: unknown) => (typeof value === 'string' && value.trim() !== '' ? value.trim() : undefined)
  const instructions = text(args.instructions)
  return { ...(instructions !== undefined && { instructions }), resume: text(args.resume) ?? RESUME_DEFAULT }
}

const n = (value: number) => value.toLocaleString('en-US')

/**
 * The compact tool as the model reads it. `threshold` is where the engine
 * compacts on its own; undefined when the window could not be read.
 */
export function describeCompact(threshold: number | undefined): string {
  const own = threshold === undefined ? "near the window's end" : `at about ${n(threshold)}`
  return [
    'Compact your own context at a checkpoint of your choosing.',
    '',
    'If you call this, your context is compacted when this turn ends. The',
    'compaction is one model call: you, with this very context, asked once to',
    'write the summary that replaces the conversation. The standard summary',
    'instructions apply; `instructions` adds what matters at this checkpoint.',
    'Then `resume` is submitted to you as the next prompt and you continue.',
    'Nothing else is interrupted: background shells, monitors, MCP servers and',
    'subagents keep running, and their notifications arrive afterwards. The',
    'pre-compaction transcript path is given to you after the reset, so exact',
    'details can be read back.',
    '',
    'When to compact. At a checkpoint where the summary loses no state of the',
    'current work. It cuts cumulative cache-read cost (every call re-reads the',
    'whole context), leaves room for the work ahead, and drops content that no',
    'longer matters. `context_usage` tells you where you are.',
    '- Under 150k: rarely worth it.',
    '- 150k–250k: compact when nothing is pending and nothing still needed',
    '  lives only in context.',
    '- 300k–500k: compact at any reasonable checkpoint where all work state',
    '  can be preserved. Do not wait: from here every call re-reads a large',
    '  context, and old, unrelated content degrades your reading of the rest.',
    '- Above 500k: keeping everything verbatim is justified only while the',
    '  work needs it, and not past 650–700k. Past that, make sure what',
    '  matters is in the repository where it can be read back, and compact.',
    `  The harness compacts on its own ${own}; that is a backstop, not the`,
    '  plan.',
    '',
    'How to call. As the last tool call of the turn, alone, after pending',
    'results have arrived; then end your turn without starting new work.',
    '- instructions (optional): what this checkpoint\'s summary should keep',
    '  verbatim or drop, beyond the standard summary.',
    '- resume (optional): the prompt you want to receive after the reset.',
    `  Default: "${RESUME_DEFAULT}"`,
  ].join('\n')
}

export function describeUsage(): string {
  return 'Your context size now: tokens used, the window, percent. Costs nothing. Call it when deciding whether to compact.'
}

export type ContextFigures = {
  /** Input tokens the last response was answered over. */
  tokens?: number
  /** The window the engine compacts against. */
  window: number
}

/**
 * The context_usage result: the last response's input tokens over the
 * compaction window, and where the engine compacts on its own.
 */
export function usageText(context: ContextFigures, threshold: number): string {
  const own = `The harness compacts on its own at about ${n(threshold)} tokens.`
  if (context.tokens === undefined) {
    return `Context: no model response yet this session; window ${n(context.window)} tokens. ${own}`
  }
  const percent = Math.round((context.tokens / context.window) * 100)
  return `Context: ${n(context.tokens)} of ${n(context.window)} tokens (${percent}%). ${own}`
}

/**
 * The compact tool's result: what happens next, so the model ends its turn
 * instead of waiting.
 */
export function scheduledText(request: CompactRequest): string {
  return [
    'Compaction is scheduled for the end of this turn. End your turn now without starting new work.',
    `After the reset you will be prompted with: "${request.resume}"`,
  ].join('\n')
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

/**
 * The request the compact tool took this turn, spent at the turn's end; and
 * where the engine compacts on its own, read at session start.
 */
let pending: CompactRequest | undefined
let threshold: number | undefined

/** Forgets both; for tests, which share this module. */
export function resetCompact() {
  pending = undefined
  threshold = undefined
}

/**
 * The window the engine compacts against: the compaction window where one is
 * set (client data, a setting, an experiment: /context's "Auto-compact
 * window"), else the model's. The `summary` breakdown estimates locally and
 * sends no request.
 */
async function compactionWindow($: EngineInterface): Promise<{ tokens?: number; window: number }> {
  const { context } = await $.session.usage({ breakdown: 'summary' })
  return { tokens: context.tokens, window: context.breakdown?.rawMaxTokens ?? context.window }
}

/**
 * Session start: reads the window and registers the two tools. Only a session
 * with a person at the prompt gets them: a headless (-p / SDK) session has no
 * compactor a plugin can call.
 */
export async function compactStart($: EngineInterface, _: SessionStartInput) {
  try {
    threshold = thresholdOf((await compactionWindow($)).window)
  } catch (error) {
    $.ui.log(`compact: the window could not be read: ${message(error)}`)
  }
  await $.tool.register({ name: 'context_usage', description: describeUsage(), inputSchema: { type: 'object', properties: {} } })
  await $.tool.register({
    name: 'compact',
    description: describeCompact(threshold),
    inputSchema: {
      type: 'object',
      properties: {
        instructions: { type: 'string', description: "What this checkpoint's summary should keep verbatim or drop, beyond the standard summary." },
        resume: { type: 'string', description: `The prompt to receive after the reset. Default: "${RESUME_DEFAULT}"` },
      },
    },
  })
}

/**
 * Turn start: a request still pending is stale (its turn ended by an
 * interruption or an error, not by the model's answer) and is dropped, so a
 * turn the person starts is not compacted behind them.
 */
export function compactTurnStart() {
  pending = undefined
}

/**
 * The end of a turn the model answered: the compaction it asked for, the
 * first moment after the turn is released (the engine compacts only between
 * turns), then the `resume` prompt, submitted whatever the compaction's
 * outcome, so a session nobody watches never stalls on a turn the model
 * ended to be compacted. A subagent's turn ends are not the main
 * conversation's and pass.
 */
export async function compactTurnComplete($: EngineInterface, e: TurnCompleteInput) {
  if (e.agentId !== undefined || pending === undefined) {
    return
  }
  const request = pending
  pending = undefined
  try {
    const outcome = await $.session.compact(request.instructions === undefined ? {} : { instructions: request.instructions })
    if (outcome.skip !== undefined) {
      $.ui.toast(`compact: not compacted · ${outcome.skip}`)
    }
  } catch (error) {
    $.ui.toast(`compact: ${message(error)}`)
    $.ui.log(`compact: the compaction failed: ${message(error)}`)
  }
  void $.prompt
    .submit({ text: request.resume })
    .then((entered) => {
      if (entered.drop !== undefined) {
        $.ui.toast(`compact: the resume prompt did not enter · ${entered.drop}`)
      }
    })
    .catch((error: unknown) => $.ui.toast(`compact: the resume prompt was refused · ${message(error)}`))
}

/**
 * Registers the tools and serves them. `compact` takes the request and
 * answers at once that the compaction runs when the turn ends, so the model
 * ends its turn. The session and turn events are taken with a matcher, since
 * the other mods register them too and an event is registered without one
 * once per module.
 */
export function registerCompact(on: On) {
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    await compactStart($, e)
    return next(e)
  })

  on('turn.start', (_, e, next) => {
    compactTurnStart()
    return next(e)
  })

  // After core closed the turn; the matcher keeps interrupted and errored
  // turns out, whose request turn.start then drops.
  on('turn.complete', { reason: 'answer' }, async ($, e, next) => {
    const result = await next(e)
    await compactTurnComplete($, e)
    return result
  })

  on('tool.call', { tool: 'mcp__doperpowers__context_usage' }, async ($) => {
    const context = await compactionWindow($)
    return { result: usageText(context, threshold ?? thresholdOf(context.window)) }
  })

  on('tool.call', { tool: 'mcp__doperpowers__compact' }, (_, e) => {
    if (e.agentId !== undefined) {
      return { deny: 'compact is for the main conversation; a subagent cannot compact its own context.' }
    }
    pending = readRequest(e)
    return { result: scheduledText(pending) }
  })
}
