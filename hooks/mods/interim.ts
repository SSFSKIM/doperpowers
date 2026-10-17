import type { On } from 'claude-code'

/**
 * The note the engine writes into an agent's completion notification when the
 * agent ended its turn with background work of its own still running (a
 * subagent waiting on its own subagent or shell). The same task-id notifies
 * again when that work wakes it.
 */
export const INTERIM_NOTE = 'This agent stopped with background work of its own still running.'

/**
 * The results the engine writes in place of the agent's own words when the
 * report goes, or will go, through SubagentHandback: still waiting, or
 * already delivered as a message (plainly, or under an auto-mode security
 * warning). The whole result must be one of these; any other text, the
 * agent's or the engine's, makes it a result worth delivering.
 */
export const PLACEHOLDERS = [
  /^This agent has not reported yet: it is waiting on its own background work and will deliver its report through SubagentHandback when that finishes\.$/,
  /^This agent's report was delivered to you as a message from "[^"\n]*" \(its SubagentHandback call\)(?:, under a SECURITY WARNING from auto mode \u2014 the warning above the report says why)?\. Read it there; it is not repeated here\.$/,
]

const element = (text: string, tag: string) =>
  new RegExp(`^<${tag}>([\\s\\S]*?)</${tag}>$`, 'm').exec(text)?.[1]

export function isInterim(text: string): boolean {
  if (!text.trimStart().startsWith('<task-notification>')) {
    return false
  }
  if (element(text, 'status')?.trim() !== 'completed' || !element(text, 'note')?.startsWith(INTERIM_NOTE)) {
    return false
  }
  const result = element(text, 'result')?.trim()
  return result !== undefined && PLACEHOLDERS.some((placeholder) => placeholder.test(result))
}

/**
 * Drops an interim agent notification that carries nothing but a placeholder
 * before it enters the session: otherwise each one wakes the receiving
 * session for a turn with nothing to act on. One whose result is the agent's
 * own text, the final one, and every other notification pass as they came.
 */
export function registerInterim(on: On) {
  on('prompt.submit', { origin: { kind: 'task-notification' } }, async (_$, e, next) => {
    if (isInterim(e.text)) {
      return { drop: 'interim agent notification: its work is still running' }
    }
    return next(e)
  })
}
