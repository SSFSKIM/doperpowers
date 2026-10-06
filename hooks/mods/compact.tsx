import type { EngineInterface, On, SessionStartInput, ToolDescribeResult, TurnCompleteInput } from 'claude-code'

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
    'Compact your own context at a reasonable checkpoint of your choosing. Runs when',
    'this turn ends: you write the summary that replaces the conversation',
    '(standard instructions plus your `instructions`), then `resume` is',
    'submitted to you as the next prompt. Background shells, monitors, MCP',
    'servers and subagents keep running; the pre-compaction transcript path',
    'is given to you afterwards.',
    '',
    'When. At each reasonable checkpoint, call `context_usage` and judge;',
    'compact only where no state of the current work is lost.',
    '- Under 150k: rarely.',
    '- 150k–250k: when nothing is pending and nothing still needed lives',
    '  only in context.',
    '- 300k–500k: at any reasonable checkpoint. Do not wait for a full',
    '  context: old or unrelated content degrades your reading of the rest;',
    '  if that is not the case, or justified, continue.',
    '- Above 500k: verbatim retention only while the work needs it; try not',
    '  to pass 650–700k unless truly justified. Past that, put what matters',
    `  in the repository, then compact. The harness compacts on its own ${own}:`,
    '  a backstop, not the plan.',
    '',
    'How. Last tool call of the turn, alone, after pending results arrived;',
    'then end your turn.',
    '- instructions (optional): what to keep verbatim or drop beyond the',
    '  standard summary.',
    `- resume (optional): the prompt to receive after the reset; default`,
    `  "${RESUME_DEFAULT}"`,
  ].join('\n')
}

export function describeUsage(): string {
  return 'Your context size now: tokens used, window, percent. Free. Call it at each reasonable checkpoint to judge whether to compact.'
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

/** A tool.describe answer that keeps the tool out of tool-search deferral. */
const inline = (described: ToolDescribeResult): ToolDescribeResult => ({ ...described, isDeferred: false }) as ToolDescribeResult

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
        instructions: { type: 'string', description: 'What to keep verbatim or drop, beyond the standard summary.' },
        resume: { type: 'string', description: `The prompt to receive after the reset; default "${RESUME_DEFAULT}"` },
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

  // Tool search defers every MCP tool, and these two are MCP tools to the
  // engine: the model would see their names alone and read the guidance only
  // after loading one. A tool.describe verdict of isDeferred: false keeps
  // them inline (the engine's own placement, passed as e.isDeferred, loses).
  on('tool.describe', { tool: 'mcp__doperpowers__compact' }, async (_, e, next) => inline(await next(e)))
  on('tool.describe', { tool: 'mcp__doperpowers__context_usage' }, async (_, e, next) => inline(await next(e)))

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
