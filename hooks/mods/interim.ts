import type { On } from 'claude-code'

/**
 * The note the engine writes into an agent's completion notification when the
 * agent ended its turn with background work of its own still running (a
 * subagent waiting on its own subagent or shell). The same task-id notifies
 * again when that work wakes it, so this one reports nothing yet.
 */
export const INTERIM_NOTE = 'This agent stopped with background work of its own still running.'

export function isInterim(text: string): boolean {
  return text.trimStart().startsWith('<task-notification>') && text.includes(INTERIM_NOTE)
}

/**
 * Drops an interim agent notification before it enters the session: otherwise
 * each one wakes the receiving session for a turn with nothing to act on. The
 * agent's final notification, and every other one, passes as it came.
 */
export function registerInterim(on: On) {
  on('prompt.submit', { origin: { kind: 'task-notification' } }, async (_$, e, next) => {
    if (isInterim(e.text)) {
      return { drop: 'interim agent notification: its work is still running' }
    }
    return next(e)
  })
}
