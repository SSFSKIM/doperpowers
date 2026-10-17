import type { EngineInterface, On, SessionMessage, ToolDescribeResult } from 'claude-code'

import {
  APPEAL_DESCRIPTION,
  APPEAL_SCHEMA,
  JUDGE_SYSTEM,
  REPORT_DAYS,
  SUGGEST_SYSTEM,
  TRUSTED_SOURCES,
  type Block,
  type EvidenceParts,
  type Ledger,
  type LogEvent,
  aggregate,
  appealCheck,
  applyRuling,
  blockNotice,
  blockReason,
  bumpEpoch,
  isAppealable,
  judgePrompt,
  logLine,
  newLedger,
  parseRuling,
  recordBlock,
  recordFailure,
  reportText,
  rulingText,
  settingsEvidence,
  suggestPrompt,
  takePass,
} from './appeal-judge'
import { asyncAsks } from './ask'

/**
 * The tool as the model names it, `mcp__<plugin>__<name>` with the plugin's
 * manifest name; written out so the engine's scan reads the matchers.
 */
export const APPEAL = 'mcp__doperpowers__appeal'

const RESERVED = new Set(['tool', 'tool_use_id', 'consent', 'agentId', 'requestMeta'])

/** A tool call's own arguments. */
const toolInput = (e: Record<string, unknown>) => Object.fromEntries(Object.entries(e).filter(([k]) => !RESERVED.has(k)))

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

/** A tool.describe answer that keeps the tool out of tool-search deferral. */
const inline = (described: ToolDescribeResult): ToolDescribeResult => ({ ...described, isDeferred: false }) as ToolDescribeResult

/**
 * The session's ledger, and its log: one file per session, seeded from what
 * the file held at start and rewritten whole on each event, the writes in
 * order. Module memory: a hot reload forgets open blocks and passes.
 */
let ledger: Ledger = newLedger()
let log: { path: string; lines: string[]; writing: Promise<void> } | undefined

/** Forgets both; for tests, which share this module. */
export function resetAppeal() {
  ledger = newLedger()
  log = undefined
}

async function record($: EngineInterface, event: LogEvent) {
  if (log === undefined) {
    return
  }
  const own = log
  own.lines.push(logLine(await $.clock.now(), event))
  // Each write waits for the one before it, so a later event's snapshot is
  // never overwritten by an earlier one's finishing last.
  own.writing = own.writing.then(() => $.fs.write(own.path, `${own.lines.join('\n')}\n`)).catch((error: unknown) => {
    $.ui.log(`appeal: the log could not be written: ${message(error)}`)
  })
  await own.writing
}

/**
 * Session start: the log, with the events a file of this session already
 * holds (a reload, a resume), and the tool, in every loop. A headless run in
 * auto mode is blocked too, so no `isInteractive` matcher.
 */
export async function appealStart($: EngineInterface) {
  const home = await $.env.get('HOME')
  if (home !== undefined) {
    const path = `${home}/.claude/appeals/${await $.session.id()}.jsonl`
    let lines: string[] = []
    try {
      if (await $.fs.exists(path)) {
        lines = (await $.fs.read(path)).split('\n').filter((l) => l.trim() !== '')
      }
    } catch (error) {
      $.ui.log(`appeal: the log could not be read: ${message(error)}`)
    }
    log = { path, lines, writing: Promise.resolve() }
  }
  await $.tool.register({ name: 'appeal', description: APPEAL_DESCRIPTION, inputSchema: APPEAL_SCHEMA })
  await $.command.register({ name: 'appeals', description: 'The auto-mode blocks appealed in the last 30 days, and the autoMode entries the grants suggest.' })
}

/**
 * `/appeals`: every session's log from the last 30 days, the counts and the
 * grants, and — when there are grants — the entries the judge model would
 * add to the user's autoMode settings, printed for the person to apply.
 */
export async function appealsReport($: EngineInterface): Promise<string> {
  const home = await $.env.get('HOME')
  if (home === undefined) {
    return 'No appeal log: HOME is not set.'
  }
  const dir = `${home}/.claude/appeals`
  const since = (await $.clock.now()) - REPORT_DAYS * 24 * 60 * 60 * 1000
  const files: { text: string }[] = []
  if (await $.fs.exists(dir)) {
    for (const entry of await $.fs.list(dir)) {
      if (entry.kind === 'file' && entry.name.endsWith('.jsonl') && entry.mtimeMs >= since) {
        files.push({ text: await $.fs.read(`${dir}/${entry.name}`) })
      }
    }
  }
  const report = aggregate(files)
  let suggestions: string | undefined
  if (report.grants.length > 0) {
    const user = (await $.settings.read({ source: 'user' })) as { autoMode?: unknown }
    const reply = await $.model.complete({
      model: (await $.env.get('DOPERPOWERS_APPEAL_MODEL')) ?? 'opus',
      system: SUGGEST_SYSTEM,
      prompt: suggestPrompt(report, user.autoMode),
      effort: 'high',
      maxTokens: 4000,
      timeoutMs: 120_000,
    })
    suggestions = reply.isAnswered ? reply.text : `(no suggestions: the model gave no answer — ${reply.reason})`
  }
  return reportText(report, suggestions)
}

/**
 * The user's standing words the judge reads: the instruction files (each
 * skipped when absent) and, source by source, the settings the classifier
 * itself trusts.
 */
async function instructions($: EngineInterface): Promise<{ name: string; text: string }[]> {
  const home = await $.env.get('HOME')
  const root = await $.session.root()
  const paths = [
    ...(home === undefined ? [] : [{ path: `${home}/.claude/CLAUDE.md`, name: `${home}/.claude/CLAUDE.md (the user's own)` }]),
    { path: `${root}/CLAUDE.md`, name: `${root}/CLAUDE.md (in the repository)` },
    { path: `${root}/CLAUDE.local.md`, name: `${root}/CLAUDE.local.md (in the repository, untracked)` },
  ]
  const found: { name: string; text: string }[] = []
  for (const { path, name } of paths) {
    try {
      if (await $.fs.exists(path)) {
        found.push({ name, text: await $.fs.read(path) })
      }
    } catch (error) {
      $.ui.log(`appeal: ${path} could not be read: ${message(error)}`)
    }
  }
  for (const source of TRUSTED_SOURCES) {
    try {
      found.push(...settingsEvidence(source, (await $.settings.read({ source })) as Record<string, unknown>))
    } catch (error) {
      $.ui.log(`appeal: the ${source} settings could not be read: ${message(error)}`)
    }
  }
  return found
}

/** The evidence the judge reads for this block, gathered from the engine. */
async function evidence($: EngineInterface, block: Block, argument: string): Promise<EvidenceParts> {
  const answers = asyncAsks()
    .filter((ask) => ask.status === 'answered' && ask.answer !== undefined)
    .map((ask) => ({ questions: ask.questions.map((q) => q.question), answer: ask.answer ?? '' }))
  const main = await $.session.messages()
  const agent = block.agentId === undefined ? undefined : await $.session.messages({ agentId: block.agentId })
  return { block, argument, instructions: await instructions($), answers, main, agent: agent as readonly SessionMessage[] | { deny: string } | undefined }
}

/** An appeal: the checks, the judge, the ruling, in the tool's own result. */
export async function appeal($: EngineInterface, e: { agentId?: string; block?: unknown; argument?: unknown }): Promise<{ result: string }> {
  // Read before the first await: a prompt from here on makes the evidence stale.
  const epoch = ledger.epoch
  const checked = appealCheck(ledger, e.block, e.agentId, e.argument)
  if (!checked.ok) {
    return { result: `Not appealed: ${checked.error}` }
  }
  const { block } = checked
  const argument = (e.argument as string).trim()
  const model = (await $.env.get('DOPERPOWERS_APPEAL_MODEL')) ?? 'opus'
  const started = await $.clock.now()
  const failed = async (reason: string) => {
    await record($, { event: 'no-ruling', block: block.id, reason })
    return { result: recordFailure(block, reason) }
  }
  let reply: Awaited<ReturnType<EngineInterface['model']['complete']>>
  try {
    const prompt = judgePrompt(await evidence($, block, argument))
    reply = await $.model.complete({ model, system: JUDGE_SYSTEM, prompt, effort: 'high', maxTokens: 8000, timeoutMs: 180_000 })
  } catch (error) {
    return failed(message(error))
  }
  if (!reply.isAnswered) {
    return failed(reply.reason === 'api-error' ? `api-error ${reply.status ?? ''}`.trim() : reply.reason)
  }
  const ruling = parseRuling(reply.text)
  if (ruling === undefined) {
    return failed('the judge gave no verdict')
  }
  if (ledger.epoch !== epoch) {
    return failed('a prompt arrived while the judge was reading, so its evidence is stale')
  }
  const now = await $.clock.now()
  applyRuling(ledger, block, ruling.verdict, now)
  await record($, {
    event: 'ruling',
    block: block.id,
    verdict: ruling.verdict,
    response: ruling.response,
    argument,
    model,
    durationMs: now - started,
    usage: reply.usage,
  })
  $.ui.toast(`appeal ${block.id} ${ruling.verdict === 'grant' ? 'granted' : 'upheld'}: ${block.tool}`)
  return { result: rulingText(block, ruling.verdict, ruling.response) }
}

/**
 * Registers the tool and the hooks: a classifier block gets an id and a note;
 * the tool rules through the judge; a pass lets the identical re-run through
 * where core's own verdict is the plain ask the blocked call reached; a
 * prompt submitted ends every outstanding pass.
 */
export function registerAppeal(on: On) {
  on('session.start', { cwd: /^/ }, async ($, e, next) => {
    await appealStart($)
    return next(e)
  })

  on('tool.describe', { tool: 'mcp__doperpowers__appeal' }, async (_, e, next) => inline(await next(e)))

  on('command.run', { command: 'appeals' }, async ($) => ({ text: await appealsReport($) }))

  // Every call: a result that is a classifier block is given its id.
  on('tool.call', { tool: /^/ }, async ($, e, next) => {
    const result = await next(e)
    if (result.isError !== true || typeof result.text !== 'string') {
      return result
    }
    const reason = blockReason(result.text)
    if (reason === undefined || !isAppealable(reason)) {
      return result
    }
    const block = recordBlock(ledger, { agentId: e.agentId, tool: e.tool, input: toolInput(e as Record<string, unknown>), reason }, await $.clock.now())
    await record($, { event: 'block', block: block.id, agentId: e.agentId ?? null, tool: e.tool, input: block.input, reason, cwd: await $.session.cwd() })
    return { ...result, context: [...(result.context ?? []), blockNotice(block.id)] }
  }).catch((_, e, next) => next(e))

  on('tool.call', { tool: 'mcp__doperpowers__appeal' }, ($, e) => appeal($, e as { agentId?: string; block?: unknown; argument?: unknown }))

  // The pass: only over core's plain ask, never over a rule, a classic hook,
  // a setting's own check, a host's ask, or an organization's ceiling.
  on('tool.check', { tool: /^/ }, async ($, e, next) => {
    const verdict = await next(e)
    if (
      verdict.decision !== 'ask' ||
      verdict.rule !== undefined ||
      verdict.hook !== undefined ||
      verdict.setting !== undefined ||
      verdict.decider !== undefined ||
      e.ceiling !== undefined ||
      typeof e.tool_use_id !== 'string'
    ) {
      return verdict
    }
    const pass = takePass(ledger, e.agentId, e.tool, e.input, await $.clock.now())
    if (pass === undefined) {
      return verdict
    }
    await record($, { event: 'used', block: pass.block })
    return { decision: 'allow', reason: `appeal ${pass.block} granted` }
  }).catch((_, e, next) => next(e))

  // Any prompt — the user's words, or anything that starts a turn in their
  // place — ends the passes: what a judge ruled on may no longer be wanted.
  on('prompt.submit', { text: /^/ }, (_, e, next) => {
    bumpEpoch(ledger)
    return next(e)
  }).catch((_, e, next) => next(e))
}
