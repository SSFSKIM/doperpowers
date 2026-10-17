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

const INTERIM_NOTE_IN_FULL = `${INTERIM_NOTE} It may resume on its own when that work completes or reports, and the same task-id notifies again if it does; the result below may be interim.`

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const line = (tag: string) => `(?:\\n<${tag}>[^<\\n]*</${tag}>)`

/**
 * The whole of an interim notification as the engine builds it (`ci` around
 * `oRt`'s body), and nothing else: its header lines, the interim note alone,
 * one result, and the usage and worktree lines. Every value the engine
 * escapes or writes itself holds no `<`, so a second notification, an extra
 * element, a clause appended to the note, a warning beside the result, or
 * text before or after the envelope makes the text something else.
 */
const ENVELOPE = new RegExp([
  '^<task-notification>',
  `${line('task-id')}`,
  `${line('tool-use-id')}?`,
  `${line('task-type')}?`,
  `${line('output-file')}?`,
  '\\n<status>completed</status>',
  `${line('summary')}?`,
  `\\n<note>${escape(INTERIM_NOTE_IN_FULL)}</note>`,
  '\\n<result>([^<]*)</result>',
  '(?:\\n<usage><subagent_tokens>\\d+</subagent_tokens><tool_uses>\\d+</tool_uses><duration_ms>\\d+</duration_ms></usage>)?',
  '(?:\\n<worktree><worktreePath>[^<\\n]*</worktreePath>(?:<worktreeBranch>[^<\\n]*</worktreeBranch>)?</worktree>)?',
  '\\n</task-notification>$',
].join(''))

export function isInterim(text: string): boolean {
  const result = ENVELOPE.exec(text.trim())?.[1]?.trim()
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
