import type { On } from 'claude-code'

/**
 * Eval-only. Both configurations' fetch calls pass through here first: one
 * whose URL goes through a third-party reader or proxy is denied, for the
 * reason Bash is left out of both (each configuration reads the web through its
 * own fetch tool). The check is `web/evals/deny_readers.py`, which holds the
 * hosts and its tests; a settings hook could not do this, as the engine runs
 * none for a mod's tool.
 *
 * Only a clean pass (exit 0) lets the call through. A check that fails is
 * a harness error, never a pass: the call is denied with text that opens
 * `HARNESS_ERROR` (harness.py), and the report holds such a run invalid.
 */
const HARNESS_ERROR = 'eval harness error:'

export function register(on: On) {
  on('tool.call', { tool: /^(WebFetch|mcp__web__fetch)$/ }, async ($, e, next) => {
    const event = JSON.stringify({ tool_name: e.tool, tool_input: { url: (e as { url?: unknown }).url } })
    const ran = await $.process.run(['python3', '-I', `${$.plugin.root}/../deny_readers.py`], { stdin: event, timeoutMs: 10_000 })
    if (ran.exitCode === 0) return next(e)
    if (ran.exitCode === 2) return { deny: ran.stderr.trim() }
    return { deny: `${HARNESS_ERROR} the reader check failed (exit ${ran.exitCode}): ${ran.stderr.trim().slice(0, 300)}` }
  }).catch((_, e, next) => ({ deny: `${HARNESS_ERROR} the reader check could not run (${next.error.kind}${next.error.message ? `: ${next.error.message}` : ''})` }))
}
