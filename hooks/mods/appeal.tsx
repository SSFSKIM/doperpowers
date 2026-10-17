import type { EngineInterface, On, SessionMessage, ToolDescribeResult } from 'claude-code'

import {
  APPEAL_DESCRIPTION,
  APPEAL_SCHEMA,
  JUDGE_SYSTEM,
  type Block,
  type EvidenceParts,
  type Ledger,
  type LogEvent,
  appealCheck,
  applyRuling,
  blockNotice,
  blockReason,
  isAppealable,
  judgePrompt,
  logLine,
  newLedger,
  parseRuling,
  recordBlock,
  recordFailure,
  rulingText,
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
 * The session's ledger, and its log: one file per session, rewritten whole
 * on each event. Module memory: a hot reload forgets open blocks and passes.
 */
let ledger: Ledger = newLedger()
let log: { path: string; lines: string[] } | undefined

/** Forgets both; for tests, which share this module. */
export function resetAppeal() {
  ledger = newLedger()
  log = undefined
}

async function record($: EngineInterface, event: LogEvent) {
  if (log === undefined) {
    return
  }
  log.lines.push(logLine(await $.clock.now(), event))
  try {
    await $.fs.write(log.path, `${log.lines.join('\n')}\n`)
  } catch (error) {
    $.ui.log(`appeal: the log could not be written: ${message(error)}`)
  }
}

/**
 * Session start: the log's path, and the tool, in every loop. A headless run
 * in auto mode is blocked too, so no `isInteractive` matcher.
 */
export async function appealStart($: EngineInterface) {
  const home = await $.env.get('HOME')
  if (home !== undefined) {
    log = { path: `${home}/.claude/appeals/${await $.session.id()}.jsonl`, lines: [] }
  }
  await $.tool.register({ name: 'appeal', description: APPEAL_DESCRIPTION, inputSchema: APPEAL_SCHEMA })
}

/** The instruction files the judge reads, each skipped when absent. */
async function instructions($: EngineInterface): Promise<{ name: string; text: string }[]> {
  const home = await $.env.get('HOME')
  const root = await $.session.root()
  const paths = [...(home === undefined ? [] : [`${home}/.claude/CLAUDE.md`]), `${root}/CLAUDE.md`, `${root}/CLAUDE.local.md`]
  const found: { name: string; text: string }[] = []
  for (const path of paths) {
    try {
      if (await $.fs.exists(path)) {
        found.push({ name: path, text: await $.fs.read(path) })
      }
    } catch (error) {
      $.ui.log(`appeal: ${path} could not be read: ${message(error)}`)
    }
  }
  const settings = (await $.settings.read()) as { autoMode?: unknown }
  found.push({ name: 'autoMode settings', text: JSON.stringify(settings.autoMode ?? null, null, 1) })
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
  const checked = appealCheck(ledger, e.block, e.agentId, e.argument)
  if (!checked.ok) {
    return { result: `Not appealed: ${checked.error}` }
  }
  const { block } = checked
  const argument = (e.argument as string).trim()
  const model = (await $.env.get('DOPERPOWERS_APPEAL_MODEL')) ?? 'opus'
  const started = await $.clock.now()
  let reply: Awaited<ReturnType<EngineInterface['model']['complete']>>
  try {
    const prompt = judgePrompt(await evidence($, block, argument))
    reply = await $.model.complete({ model, system: JUDGE_SYSTEM, prompt, effort: 'high', maxTokens: 8000, timeoutMs: 180_000 })
  } catch (error) {
    await record($, { event: 'no-ruling', block: block.id, reason: message(error) })
    return { result: recordFailure(block, message(error)) }
  }
  if (!reply.isAnswered) {
    const reason = reply.reason === 'api-error' ? `api-error ${reply.status ?? ''}`.trim() : reply.reason
    await record($, { event: 'no-ruling', block: block.id, reason })
    return { result: recordFailure(block, reason) }
  }
  const ruling = parseRuling(reply.text)
  if (ruling === undefined) {
    await record($, { event: 'no-ruling', block: block.id, reason: 'the judge gave no verdict' })
    return { result: recordFailure(block, 'the judge gave no verdict') }
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
 * where core's own verdict is the plain ask the blocked call reached.
 */
export function registerAppeal(on: On) {
  on('session.start', { cwd: /^/ }, async ($, e, next) => {
    await appealStart($)
    return next(e)
  })

  on('tool.describe', { tool: 'mcp__doperpowers__appeal' }, async (_, e, next) => inline(await next(e)))

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
}
