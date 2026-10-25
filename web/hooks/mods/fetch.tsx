import type { On } from 'claude-code'

import { failureReply, isWhole, replyFor, textFileOf } from './reply'
import type { ClipOk, ClipResult, NumberedHeader, Summary } from './reply'
import {
  SUMMARY_MAX_OUTPUT_TOKENS,
  SUMMARY_MAX_TOKENS,
  SUMMARY_MODEL,
  SUMMARY_SYSTEM,
  SUMMARY_TIMEOUT_MS,
  isPromptTooLong,
  parseNumbered,
  summaryPrompt,
  summaryReserve,
  whyUnanswered,
} from './summary'
import type { CompletionOutcome } from './summary'

/**
 * The fetch tool (design: docs/doperpowers/specs/2026-10-25-web-fetch-design.md).
 * The clipper (`bin/clip.mjs`, a Node bundle) saves the page into the machine's
 * shared cache and prints its I1 result; this mod turns that into a reply,
 * asking `haiku` when the call has a `prompt`, and starts the cache's prune.
 */
export const FETCH_TOOL = 'mcp__web__fetch' // the name register() returns; a test pins it

export const DESCRIPTION = `Fetches a web page and saves it as a clean markdown file (images downloaded
beside it) in a cache every session and subagent on this machine shares.

- With \`prompt\`: a small fast model answers from the page, citing line
  numbers in the saved file. Use it when a gist or one fact is enough; Read
  the cited lines when the exact text matters.
- Without \`prompt\`: a short page comes back whole. A long one comes back as
  its path and an outline of line ranges and sizes; Read the sections you
  need. Use it for exact text, code, tables, or the whole argument.
- Images are files: Read one to see it.
- Pages that render with JavaScript are rendered in a headless browser.
  PDFs are saved for Read, by page.
- A copy saved in the last 24 hours is reused; \`refresh: true\` fetches again.
- Pages behind a login cannot be fetched. Local and private-network
  addresses are refused; use curl through Bash for a local server.`

export const INPUT_SCHEMA = {
  type: 'object',
  properties: {
    url: { type: 'string', format: 'uri', description: 'The page to fetch (http or https).' },
    prompt: { type: 'string', description: 'A question for a small fast model to answer from the page, citing its lines. Leave out to get the page itself.' },
    refresh: { type: 'boolean', description: 'Fetch again even when a copy saved in the last 24 hours exists.' },
  },
  required: ['url'],
}

/** The clipper's process limit: 30 s past its own 150 s deadline, so it fires only on a clipper bug. */
export const PROCESS_TIMEOUT_MS = 180_000

/** How old the cache's prune stamp may be before a session start prunes again. */
export const PRUNE_AFTER_MS = 24 * 3600_000

/**
 * Appends its standard input to the file its argument names, in one write
 * with O_APPEND, so lines from sessions writing at once do not interleave.
 * `$.fs` has no append, and the clipper's runtime is already required.
 */
export const USAGE_APPEND = "require('fs').appendFileSync(process.argv[1], require('fs').readFileSync(0))"

const NUMBERED_TIMEOUT_MS = 60_000

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

/**
 * Registers the tool as a session starts, interactive or headless (the evals
 * run `claude -p`), in the prompt's tool list rather than behind ToolSearch:
 * a tool meant to replace a habit should be in sight. A subagent's call is
 * served like the main session's.
 */
export function registerFetch(on: On) {
  on('session.start', async ($, e, next) => {
    try {
      const { tool } = await $.tool.register({ name: 'fetch', description: DESCRIPTION, inputSchema: INPUT_SCHEMA, isDeferred: false })
      if (tool !== FETCH_TOOL) $.ui.log(`web: the fetch tool registered as ${tool}, not ${FETCH_TOOL}`, { to: 'debug' })
    } catch (error) {
      $.ui.log(`web: the fetch tool is not registered: ${message(error)}`, { to: 'debug' })
    }

    // The prune, unawaited, when its stamp is a day old; a cache never pruned has none.
    const cacheDir = await $.env.get('WEB_CACHE_DIR')
    const xdg = await $.env.get('XDG_CACHE_HOME')
    const home = await $.env.get('HOME')
    const root = cacheDir || `${xdg || `${home ?? ''}/.cache`}/claude-web`
    const now = await $.clock.now()
    const stamp = await $.fs.stat(`${root}/.pruned`).catch(() => undefined)
    const isDue = stamp === undefined ? await $.fs.exists(root).catch(() => false) : now - stamp.mtimeMs > PRUNE_AFTER_MS
    if (isDue) {
      $.process
        .run(['node', `${$.plugin.root}/bin/clip.mjs`, 'prune'], { timeoutMs: 120_000 })
        .then((ran) => ran.exitCode !== 0 && $.ui.log(`web: the cache's prune failed (exit ${ran.exitCode}): ${ran.stderr.slice(0, 300)}`, { to: 'debug' }))
        .catch((error) => $.ui.log(`web: the cache's prune did not run: ${message(error)}`, { to: 'debug' }))
    }
    return next(e)
  })

  on('tool.call', { tool: FETCH_TOOL }, async ($, e) => {
    const input = e as { url?: unknown; prompt?: unknown; refresh?: unknown }
    if (typeof input.url !== 'string' || input.url.trim() === '') return { deny: 'fetch failed: no url given (an http or https URL is required)' }
    const url = input.url.trim()
    const clipper = `${$.plugin.root}/bin/clip.mjs`
    const question = typeof input.prompt === 'string' && input.prompt.trim() !== '' ? input.prompt.trim() : undefined

    // The clipper: one JSON result on stdout and exit 0, whatever the site did.
    const argv = ['node', clipper, 'fetch', url, ...(input.refresh === true ? ['--refresh'] : [])]
    const startedAt = await $.clock.now()
    let ran
    try {
      ran = await $.process.run(argv, { timeoutMs: PROCESS_TIMEOUT_MS })
    } catch (error) {
      const elapsed = (await $.clock.now()) - startedAt
      if (elapsed >= PROCESS_TIMEOUT_MS - 2000) {
        return { deny: `fetch failed: ${url}: the clipper did not finish within ${PROCESS_TIMEOUT_MS / 1000} s and was stopped (its own deadline is 150 s, so this is a bug in the web plugin): ${message(error)}` }
      }
      if (/ENOENT|not found|no such file/i.test(message(error))) {
        return { deny: `fetch failed: ${url}: node not found on PATH (the web plugin's clipper runs on Node 20 or later; install Node, or put it on the PATH Claude Code starts with): ${message(error)}` }
      }
      return { deny: `fetch failed: ${url}: the clipper could not run: ${message(error)}` }
    }
    if (ran.exitCode !== 0) {
      return { deny: `fetch failed: ${url}: the clipper failed (exit ${ran.exitCode}), a bug in the web plugin: ${ran.stderr.trim().slice(0, 1200)}` }
    }
    let result: ClipResult
    try {
      result = JSON.parse(ran.stdout) as ClipResult
    } catch {
      return { deny: `fetch failed: ${url}: the clipper's result could not be read: ${ran.stdout.slice(0, 300)}` }
    }
    if (!result.ok) return { deny: failureReply(result) }

    const textFile = textFileOf(result)
    let summary: Summary | undefined
    if (question !== undefined && textFile !== undefined) {
      summary = await summarize(result, textFile, question)
    }
    let page: string | undefined
    if (!summary?.isAnswered && isWhole(result) && textFile !== undefined) {
      try {
        page = await $.fs.read(textFile)
      } catch (error) {
        return { deny: `fetch failed: ${url}: the saved page could not be read: ${message(error)}` }
      }
    }
    return { result: replyFor(result, { now: await $.clock.now(), isAsked: question !== undefined, summary, page }) }

    /** The answer from `haiku` over the numbered page, retried once at half the cap when the prompt was too long. */
    async function summarize(r: ClipOk, file: string, ask: string): Promise<Summary> {
      const reserve = summaryReserve(ask)
      let cap = SUMMARY_MAX_TOKENS
      let previous: NumberedHeader | undefined
      let why = 'no attempt'
      for (let attempt = 0; attempt < 2; attempt++) {
        let numbered
        try {
          const out = await $.process.run(['node', clipper, 'numbered', file, '--max-tokens', String(cap), '--reserve', String(reserve)], { timeoutMs: NUMBERED_TIMEOUT_MS })
          numbered = out.exitCode === 0 ? parseNumbered(out.stdout) : undefined
          if (numbered === undefined) return { isAnswered: false, why: `the page's text could not be numbered (exit ${out.exitCode}: ${out.stderr.trim().slice(0, 200)})` }
        } catch (error) {
          return { isAnswered: false, why: `the page's text could not be numbered: ${message(error)}` }
        }
        // A half cap that keeps the same lines would ask the same question again.
        if (previous !== undefined && previous.lastLine === numbered.header.lastLine && previous.cut === numbered.header.cut) break

        const asked = await $.clock.now()
        const reply = await $.model.complete({
          model: SUMMARY_MODEL,
          system: SUMMARY_SYSTEM,
          prompt: summaryPrompt(numbered.body, ask),
          maxTokens: SUMMARY_MAX_OUTPUT_TOKENS,
          timeoutMs: SUMMARY_TIMEOUT_MS,
        })
        const elapsed = (await $.clock.now()) - asked
        await logUsage(r, reply)
        const outcome = reply as CompletionOutcome
        if (outcome.isAnswered && outcome.text.trim() !== '') {
          return { isAnswered: true, text: outcome.text, model: SUMMARY_MODEL, header: numbered.header }
        }
        why = whyUnanswered(outcome, elapsed)
        if (!isPromptTooLong(outcome)) break
        previous = numbered.header
        cap = SUMMARY_MAX_TOKENS / 2
      }
      return { isAnswered: false, why }
    }

    /**
     * One line per summary call in `<cache root>/usage.jsonl`: a completion's
     * cost stays out of the session's total, and the evals add it back from here.
     * The root is the generation folder's third parent (I2's layout).
     */
    async function logUsage(r: ClipOk, reply: { isAnswered: boolean; usage: unknown; reason?: string }) {
      const root = r.dir.split('/').slice(0, -3).join('/')
      const line = {
        time: new Date(await $.clock.now()).toISOString(),
        url: r.url,
        model: SUMMARY_MODEL,
        session: await $.session.id().catch(() => undefined),
        ...(e.agentId !== undefined && { agentId: e.agentId }),
        isAnswered: reply.isAnswered,
        ...(reply.reason !== undefined && { reason: reply.reason }),
        usage: reply.usage,
      }
      try {
        const out = await $.process.run(['node', '-e', USAGE_APPEND, `${root}/usage.jsonl`], { stdin: `${JSON.stringify(line)}\n` })
        if (out.exitCode !== 0) $.ui.log(`web: usage.jsonl was not written: ${out.stderr.slice(0, 300)}`, { to: 'debug' })
      } catch (error) {
        $.ui.log(`web: usage.jsonl was not written: ${message(error)}`, { to: 'debug' })
      }
    }
  }).catch((_, e, next) => {
    // A step that threw (a refused model request, say) still answers the call, as its error.
    const { url } = e as { url?: unknown }
    return { deny: `fetch failed: ${String(url)}: the web plugin failed (${next.error.kind}${next.error.message ? `: ${next.error.message}` : ''})` }
  })
}
