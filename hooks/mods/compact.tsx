import type { EngineInterface, On, SessionStartInput, TurnCompleteInput } from 'claude-code'

/**
 * The tool as the model names it, `mcp__<plugin>__<name>` with the plugin's
 * manifest name; written out so the engine's scan reads the matchers (the
 * hooks below name it as a literal for the same reason).
 */
export const COMPACT = 'mcp__doperpowers__compact'

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

/**
 * The offer's gate: a turn's end is offered a compaction from `floor`
 * tokens on, once the context has grown `step` since the last offer. The
 * floor is where the tool's own guidance turns to "any reasonable
 * checkpoint" (`EARLY_BELOW`); below it the model compacts unasked once
 * the work at hand is done, and is not spent a step on an offer. The step
 * keeps a conversation that adds a few k a turn from being asked every
 * turn, while a working turn (tens of k) is asked each time. `DOPERPOWERS_COMPACT_OFFER_FLOOR` and `_STEP` (tokens) override
 * them for a launch; 0 and 0 is an offer at every turn's end.
 */
export type OfferGate = { floor: number; step: number }
export const OFFER_GATE: OfferGate = { floor: 300_000, step: 70_000 }

/**
 * Below this, an offer says compacting is not necessarily recommended: the
 * description's "under about 300k" band, where only a clean checkpoint is
 * worth it. The default floor is this figure, so only a launch that lowers
 * the floor is offered below it.
 */
export const EARLY_BELOW = 300_000

/**
 * Whether a turn ending at `tokens` is offered a compaction. `last` is the
 * figure the previous offer carried, 0 before any or after a compaction.
 */
export function offerDue(tokens: number | undefined, last: number, gate: OfferGate): boolean {
  return tokens !== undefined && tokens >= gate.floor && tokens - last >= gate.step
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

/** How the offer's gate reads in the tool's description. */
function gateText(gate: OfferGate): string {
  if (gate.floor === 0 && gate.step === 0) {
    return 'at the end of every turn'
  }
  const from = gate.floor === 0 ? 'at the end of each turn' : `at the end of each turn from ${n(gate.floor)} tokens on`
  return gate.step === 0 ? from : `${from}, once it has grown ${n(gate.step)} since the last time`
}

/**
 * The compact tool as the model reads it. `threshold` is where the engine
 * compacts on its own; undefined when the window could not be read.
 */
export function describeCompact(threshold: number | undefined, gate: OfferGate = OFFER_GATE): string {
  const own = threshold === undefined ? "near the window's end" : `at about ${n(threshold)}`
  const before = gate.floor === 0 ? '' : ` Until the first time, you are under ${n(gate.floor)}.`
  return [
    'Compact your own context at a reasonable checkpoint of your choosing. Runs when',
    'this turn ends: you write the summary that replaces the conversation',
    '(standard instructions plus your `instructions`), then `resume` is',
    'submitted to you as the next prompt. Background shells, monitors, MCP',
    'servers and subagents keep running.',
    '',
    'When. Let the work decide rather than the context size: compact at a',
    'checkpoint in the work where none of its state is lost; the larger the',
    'context, the smaller a checkpoint that will do. You are told the size',
    `${gateText(gate)} (a message from the doperpowers plugin, carrying the offer).${before}`,
    'You can compact unasked at any checkpoint, mid-turn included. Size is',
    'never a reason to hurry the work or cut it short. A checkpoint is worth',
    'compacting at because stale content degrades your reading of the rest,',
    "the work ahead gets the room once this work's state is recorded, and",
    'every call re-reads the whole context, so cost grows with size.',
    'Read the size in tokens, never as a percentage of the window or of the',
    'auto-compact point: degradation and cost grow with the tokens',
    'themselves, so 300k in a 1M window is 300k, not "only 30%".',
    '- Under about 300k: when the work at hand is done, or little of',
    '  substance remains.',
    '- 300k–450k: at any reasonable checkpoint.',
    '- Above 450k: the same. Prefer not to pass 600k; go past it only while',
    '  the work needs what is in context verbatim, up to where the harness',
    `  compacts on its own ${own}: a backstop, not the plan.`,
    'Not during a design discussion, at any size: its state is the',
    'conversation itself (the reasoning, the alternatives weighed, how the',
    'human took each), which a summary flattens. Its close, once the design',
    'is written down, is the checkpoint.',
    'Prefer not to compact while a decision or work is pending: a question',
    'to the human not yet answered, a decision you are still weighing, a',
    'subagent or background job whose result you will judge against what',
    'sent it. Settling it takes the context that raised it, whole.',
    '',
    'How. Last tool call of the turn, alone, after pending results arrived;',
    'then end your turn.',
    '- instructions (optional): what to keep verbatim or drop beyond the',
    '  standard summary.',
    `- resume (optional): the prompt to receive after the reset; default`,
    `  "${RESUME_DEFAULT}"`,
  ].join('\n')
}

export type ContextFigures = {
  /** Input tokens the last response was answered over. */
  tokens?: number
  /** The window the engine compacts against. */
  window: number
}

/**
 * The figures as the offer states them: the last response's input tokens,
 * the compaction window, and where the engine compacts on its own. No
 * percentage: the model is to weigh the count itself, which a share of a 1M
 * window understates.
 */
export function usageText(context: ContextFigures, threshold: number): string {
  const own = `The harness compacts on its own at about ${n(threshold)} tokens.`
  if (context.tokens === undefined) {
    return `Context: no model response yet this session; window ${n(context.window)} tokens. ${own}`
  }
  return `Context: ${n(context.tokens)} tokens; window ${n(context.window)}. ${own}`
}

/**
 * The offer, as a prompt of the plugin's that starts a turn of its own once
 * the turn it follows has ended (the model reads it under "The doperpowers
 * plugin sent a message:", and the report view folds it into the working
 * record, which a Stop hook's row could not be). The tool waits behind tool
 * search, so the offer sends the model to its description, which says when
 * a checkpoint is worth it, before it decides. The decline is a line, not
 * silence: an answer with no text costs the engine's "no visible output"
 * nudge, one more step. Below `EARLY_BELOW` it says compacting is not
 * necessarily recommended.
 */
export function offerText(context: ContextFigures, threshold: number): string {
  const early =
    context.tokens !== undefined && context.tokens < EARLY_BELOW
      ? [
          `Below ${n(EARLY_BELOW)} tokens, compacting is not necessarily recommended unless this is a`,
          'clean checkpoint: no key execution, decision, design or architecting pending that',
          "needs the prior context's information and nuance as a whole.",
        ]
      : []
  return [
    usageText(context, threshold),
    ...early,
    "Before you decide, read mcp__doperpowers__compact's description: it says when a",
    'checkpoint is worth it (if the tool is not loaded, ToolSearch with',
    '"select:mcp__doperpowers__compact" loads it). If you truly think this is the right',
    'time to compact, compact now with it (alone, then end your turn). Otherwise',
    'reply "Not compacting." (one line, a reason optional) and end your turn.',
  ].join('\n')
}

/**
 * What an offer says instead when a compaction stood between its submission
 * and its turn (a `/compact` the person queued, the model compacting in a
 * turn the person queued ahead of it): its figures are gone, and it cannot
 * be withdrawn without the engine's "Prompt dropped by a hook" notice.
 */
export function compactedOfferText(): string {
  return [
    'Context: compacted since this offer was made, so there is nothing to decide now.',
    'Reply "Not compacting." (one line) and end your turn.',
  ].join('\n')
}

/**
 * Whether a prompt is an offer: what `offerText` writes opens with the
 * figures and asks for the decline line. Read from the text rather than
 * remembered, so a module reloaded while its offer waits in the queue still
 * knows the offer's turn when it starts.
 */
export function isOfferText(text: string): boolean {
  return text.startsWith('Context: ') && text.includes('reply "Not compacting."')
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
 * The request the compact tool took this turn, spent at the turn's end;
 * where the engine compacts on its own, read at session start; whether the
 * tool is registered (a session the offer may name it in); the offer's gate
 * and the figure its last offer carried; whether a Stop hook beneath set
 * `preventContinuation` in this main turn; the offer in flight, `queued`
 * once submitted and `entering` once it passed `prompt.submit`, until its
 * turn starts, and whether a compaction has stood since it was submitted;
 * and whether the running main turn is an offer's own.
 */
let pending: CompactRequest | undefined
let threshold: number | undefined
let registered = false
let gate: OfferGate = OFFER_GATE
let lastOffered = 0
let prevented = false
let offer: 'queued' | 'entering' | undefined
let compactedSinceOffer = false
let offerTurn = false

/** Forgets all of it; for tests, which share this module. */
export function resetCompact() {
  pending = undefined
  threshold = undefined
  registered = false
  gate = OFFER_GATE
  lastOffered = 0
  prevented = false
  offer = undefined
  compactedSinceOffer = false
  offerTurn = false
}

/** A main-conversation compaction stood: the baseline starts over, and an offer in flight lost its figures. */
function compacted() {
  lastOffered = 0
  if (offer !== undefined) {
    compactedSinceOffer = true
  }
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

/** The gate, with each figure the environment overrides (a whole number of tokens). */
async function gateOf($: EngineInterface): Promise<OfferGate> {
  const figure = (value: string | undefined, fallback: number) => {
    const parsed = value === undefined ? NaN : Number(value)
    return Number.isInteger(parsed) && parsed >= 0 ? parsed : fallback
  }
  return {
    floor: figure(await $.env.get('DOPERPOWERS_COMPACT_OFFER_FLOOR'), OFFER_GATE.floor),
    step: figure(await $.env.get('DOPERPOWERS_COMPACT_OFFER_STEP'), OFFER_GATE.step),
  }
}

/**
 * Session start: reads the window and the gate and registers the tool. Only
 * a session with a person at the prompt gets it: a headless (-p / SDK)
 * session has no compactor a plugin can call.
 */
export async function compactStart($: EngineInterface, _: SessionStartInput) {
  try {
    threshold = thresholdOf((await compactionWindow($)).window)
  } catch (error) {
    $.ui.log(`compact: the window could not be read: ${message(error)}`)
  }
  gate = await gateOf($)
  await $.tool.register({
    name: 'compact',
    description: describeCompact(threshold, gate),
    inputSchema: {
      type: 'object',
      properties: {
        instructions: { type: 'string', description: 'What to keep verbatim or drop, beyond the standard summary.' },
        resume: { type: 'string', description: `The prompt to receive after the reset; default "${RESUME_DEFAULT}"` },
      },
    },
  })
  registered = true
}

/**
 * Turn start: a request still pending is stale (its turn ended by an
 * interruption or an error, not by the model's answer) and is dropped, so a
 * turn the person starts is not compacted behind them. The turn an entering
 * offer starts is the offer's own. A subagent's turn start (it carries the
 * agentId) is not the main conversation's and passes.
 */
export function compactTurnStart(e: { agentId?: string }) {
  if (e.agentId !== undefined) {
    return
  }
  pending = undefined
  prevented = false
  offerTurn = offer === 'entering'
  if (offerTurn) {
    offer = undefined
  }
}

/**
 * The main conversation's Stop, as the hooks beneath answered it: whether
 * one set `preventContinuation`, which withholds the offer at this turn's
 * end. The last Stop of the turn decides.
 */
export function compactStop(e: { agent_id?: string }, answered: { preventContinuation?: true }) {
  if (e.agent_id === undefined) {
    prevented = answered.preventContinuation === true
  }
}

/**
 * The offer, where one is due at the end of a main turn the model answered
 * and asked no compaction in: submitted as the plugin's prompt, which the
 * engine runs as a turn of its own once the session is idle, behind any
 * prompt the person queued. None at the end of an offer's own turn, while
 * one waits to enter, when a Stop hook beneath prevented continuation, in a
 * session without the tool (headless), or when the figures cannot be read.
 * The submission is not awaited: it resolves once the offer's turn starts,
 * after this hook has returned.
 */
async function offerAtTurnEnd($: EngineInterface) {
  if (!registered || offerTurn || offer !== undefined || prevented) {
    return
  }
  let context: ContextFigures
  try {
    context = await compactionWindow($)
  } catch (error) {
    $.ui.log(`compact: the figures could not be read at the turn's end: ${message(error)}`)
    return
  }
  // A compaction on a path that raised no session.compact event is still
  // observed here, even below the offer's floor.
  if (context.tokens !== undefined && context.tokens < lastOffered) {
    lastOffered = 0
  }
  if (!offerDue(context.tokens, lastOffered, gate)) {
    return
  }
  const baseline = lastOffered
  lastOffered = context.tokens ?? 0
  compactedSinceOffer = false
  offer = 'queued'
  const settled = (why: string | undefined) => {
    if (offer === 'queued') {
      // It never passed this module's prompt.submit: the engine removed it
      // from the queue before it ran, or a hook above answered it. It never
      // ran, so the baseline it replaced comes back, unless a compaction
      // has started the baseline over since.
      offer = undefined
      if (!compactedSinceOffer) {
        lastOffered = baseline
      }
    }
    if (why !== undefined) {
      $.ui.log(`compact: the offer did not enter · ${why}`, { to: 'debug' })
    }
  }
  void $.prompt
    .submit({ text: offerText(context, threshold ?? thresholdOf(context.window)) })
    .then((entered) => settled(entered.drop))
    .catch((error: unknown) => settled(message(error)))
}

/**
 * The offer as it enters, its figures read again: a prompt the person
 * queued, or a notification, runs ahead of it and grows the context in its
 * turn. The figure it carries becomes the last offer's. After a compaction
 * that stood since it was submitted, or with no figure to read (the engine
 * has none until the first response after a compaction), it says there is
 * nothing to decide. Figures that cannot be read leave the text as written.
 */
async function enteringOffer($: EngineInterface, text: string): Promise<string> {
  if (compactedSinceOffer) {
    return compactedOfferText()
  }
  let context: ContextFigures
  try {
    context = await compactionWindow($)
  } catch (error) {
    $.ui.log(`compact: the offer's figures could not be read again: ${message(error)}`, { to: 'debug' })
    return text
  }
  if (context.tokens === undefined) {
    return compactedOfferText()
  }
  lastOffered = context.tokens
  return offerText(context, threshold ?? thresholdOf(context.window))
}

/**
 * The end of a turn the model answered: the compaction it asked for, the
 * first moment after the turn is released (the engine compacts only between
 * turns), then the `resume` prompt, submitted whatever the compaction's
 * outcome, so a session nobody watches never stalls on a turn the model
 * ended to be compacted; else the offer, where it is due. A subagent's turn
 * ends are not the main conversation's and pass.
 */
export async function compactTurnComplete($: EngineInterface, e: TurnCompleteInput) {
  if (e.agentId !== undefined) {
    return
  }
  if (pending === undefined) {
    await offerAtTurnEnd($)
    return
  }
  const request = pending
  pending = undefined
  try {
    const outcome = await $.session.compact(request.instructions === undefined ? {} : { instructions: request.instructions })
    if (outcome.skip !== undefined) {
      $.ui.toast(`compact: not compacted · ${outcome.skip}`)
    } else {
      // Its rows reach the bridge (the sminos plugin's) through its own
      // session.compact hook, as the person's /compact does: the re-entry
      // rule skips only this plugin's hooks.
      compacted()
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
 * Registers the tool and serves it. `compact` takes the request and answers
 * at once that the compaction runs when the turn ends, so the model ends its
 * turn. The session, turn and prompt events are taken with a matcher, since
 * the other mods register them too and an event is registered without one
 * once per module.
 */
export function registerCompact(on: On) {
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    await compactStart($, e)
    return next(e)
  })

  // precompute keeps a summary for later; it replaces no conversation.
  on('session.compact', { trigger: /^/ }, async (_, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && e.trigger !== 'precompute' && result.skip === undefined) {
      compacted()
    }
    return result
  })

  on('turn.start', (_, e, next) => {
    compactTurnStart(e)
    return next(e)
  })

  // Read, never answered: the settings hooks beneath (smns-record.sh) keep
  // their say, and a Stop that adds nothing draws no row.
  on('classic.Stop', { hook_event_name: 'Stop' }, async (_, e, next) => {
    const result = await next(e)
    compactStop(e, result)
    return result
  })

  // After core closed the turn; the matcher keeps interrupted and errored
  // turns out, whose request turn.start then drops.
  on('turn.complete', { reason: 'answer' }, async ($, e, next) => {
    const result = await next(e)
    await compactTurnComplete($, e)
    return result
  })

  // The offer on its way into the session (a prompt of this plugin's goes
  // through every hook of it but the one that submitted it): its figures
  // read again, and the turn it starts marked as its own. Another prompt of
  // the plugin's (the resume prompt) passes untouched, as does any prompt
  // when this hook fails.
  on('prompt.submit', { origin: { kind: 'plugin', name: 'doperpowers' } }, async ($, e, next) => {
    if (!isOfferText(e.text)) {
      return next(e)
    }
    const text = await enteringOffer($, e.text)
    offer = 'entering'
    const result = await next(text === e.text ? e : { ...e, text })
    // Refused beneath (a hook, a settings hook's block): the offer stays
    // spent, so a hook that always refuses costs no submission every turn.
    if (result.drop !== undefined) {
      offer = undefined
    }
    return result
  }).catch((_, e, next) => next(e))

  on('tool.call', { tool: 'mcp__doperpowers__compact' }, (_, e) => {
    if (e.agentId !== undefined) {
      return { deny: 'compact is for the main conversation; a subagent cannot compact its own context.' }
    }
    pending = readRequest(e)
    return { result: scheduledText(pending) }
  })
}
