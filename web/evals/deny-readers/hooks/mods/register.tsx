import type { On } from 'claude-code'

/**
 * Eval-only. Both configurations' fetch calls pass through here first: one
 * whose URL goes through a third-party reader or proxy is denied, for the
 * reason Bash is left out of both (each configuration reads the web through its
 * own fetch tool). The check is `web/evals/deny_readers.py`, which holds the
 * hosts and its tests; a settings hook could not do this, as the engine runs
 * none for a mod's tool.
 */
export function register(on: On) {
  on('tool.call', { tool: /^(WebFetch|mcp__web__fetch)$/ }, async ($, e, next) => {
    const event = JSON.stringify({ tool_name: e.tool, tool_input: { url: (e as { url?: unknown }).url } })
    const ran = await $.process.run(['python3', '-I', `${$.plugin.root}/../deny_readers.py`], { stdin: event, timeoutMs: 10_000 })
    if (ran.exitCode === 2) return { deny: ran.stderr.trim() }
    return next(e)
  })
}
