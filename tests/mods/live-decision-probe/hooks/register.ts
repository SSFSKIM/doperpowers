import type { On } from 'claude-code'

/**
 * The bridge settles requests on the engine's `tool_decision` records (raised
 * to plugins through `telemetry.log`). This mod writes each one it receives to
 * the file LIVE_DECISIONS names, so live-requests-check.py can show the
 * records arrive, naming the call and who decided.
 */
const seen: Record<string, unknown>[] = []

export function register(on: On) {
  on('telemetry.log', { to: 'collector' }, async ($, e, next) => {
    if (e.to === 'collector' && e.event === 'tool_decision') {
      const path = await $.env.get('LIVE_DECISIONS')
      if (path !== undefined) {
        const { tool_use_id, source, decision, tool_name } = e.attributes
        seen.push({ tool_use_id, source, decision, tool_name, t: Date.now() })
        await $.fs.write(path, JSON.stringify(seen)).catch(() => undefined)
      }
    }
    return next(e)
  }).catch((_, e, next) => next(e))
}
