import type { EngineInterface, On } from 'claude-code'

import { subagentsDir } from './agents'

/**
 * The note the engine writes into an agent's completion notification when the
 * agent ended its turn with background work of its own still running (a
 * shell, monitor or workflow). The same task-id notifies again when that work
 * wakes it.
 */
export const INTERIM_NOTE = 'This agent stopped with background work of its own still running.'

/**
 * The result the engine writes in place of the agent's own words while the
 * report waits on that work and will come through SubagentHandback (`nTs`).
 * The engine writes it only for a task whose hand-back contract is on; an
 * agent outside the contract keeps its own words, which could be this very
 * sentence, so the text alone does not say who wrote it.
 */
export const WAITING = 'This agent has not reported yet: it is waiting on its own background work and will deliver its report through SubagentHandback when that finishes.'

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
  '\\n<task-id>(?<taskId>[^<\\n]*)</task-id>',
  `${line('tool-use-id')}?`,
  `${line('task-type')}?`,
  `${line('output-file')}?`,
  '\\n<status>completed</status>',
  `${line('summary')}?`,
  `\\n<note>${escape(INTERIM_NOTE_IN_FULL)}</note>`,
  '\\n<result>(?<result>[^<]*)</result>',
  '(?:\\n<usage><subagent_tokens>\\d+</subagent_tokens><tool_uses>\\d+</tool_uses><duration_ms>\\d+</duration_ms></usage>)?',
  '(?:\\n(?<worktree><worktree><worktreePath>[^<\\n]*</worktreePath>(?:<worktreeBranch>[^<\\n]*</worktreeBranch>)?</worktree>))?',
  '\\n</task-notification>$',
].join(''))

export type Interim = {
  taskId: string
  /** The `<worktree>` element as written: where an isolated agent's work lives. */
  worktree?: string
}

/**
 * Reads an interim notification whose whole result is the waiting
 * placeholder; anything else, the final notification among them, is not one.
 */
export function readInterim(text: string): Interim | undefined {
  const groups = ENVELOPE.exec(text.trim())?.groups
  if (groups?.taskId === undefined || groups.result?.trim() !== WAITING) {
    return undefined
  }
  return { taskId: groups.taskId, ...(groups.worktree !== undefined && { worktree: groups.worktree }) }
}

const REMINDER = '<system-reminder>\nYour final report is delivered through SubagentHandback'
const COUNTERMAND = '<system-reminder>\nSubagentHandback is not available in this run'

/**
 * The search over an agent's transcript that keeps every line that could be
 * the hand-back reminder, its countermand, or a compaction. A transcript runs
 * far past what `$.fs.read` takes (4 MiB), so `grep` reads it.
 */
export function searchArgs(path: string): string[] {
  return ['grep', '-a', '-E', 'Your final report is delivered through SubagentHandback|SubagentHandback is not available in this run|compact_boundary', '--', path]
}

/**
 * Whether the agent's run reports through SubagentHandback, as the engine
 * decides it at each run's start (`Qks`): the latest meta user record that
 * opens with the reminder or with its countermand is the reminder. Read
 * backward from the end of the lines `searchArgs` kept: a compaction met
 * before either ends the reading unanswered, since the engine's own view of
 * the run starts there, and so does a line that does not parse.
 */
export function handsBack(lines: string): boolean {
  const records = lines.split('\n')
  for (let at = records.length - 1; at >= 0; at -= 1) {
    if (records[at] === '') {
      continue
    }
    let record
    try {
      record = JSON.parse(records[at] as string)
    } catch {
      return false
    }
    if (record?.type === 'system' && record.subtype === 'compact_boundary') {
      return false
    }
    const content = record?.message?.content
    if (record?.type === 'user' && record.isMeta === true && typeof content === 'string') {
      if (content.startsWith(REMINDER)) {
        return true
      }
      if (content.startsWith(COUNTERMAND)) {
        return false
      }
    }
  }
  return false
}

type State = {
  /** The session's `subagents/` directory, once a SessionStart named it. */
  subagents?: string
  /** What notifications that entered told the session: agents by task-id, worktrees by `task-id\n<worktree>`. */
  told: Set<string>
}

/**
 * Whether the notification tells the session nothing it has not been told:
 * any worktree it carries came in an earlier one; the session knows the
 * agent, because its own loop spawned it or an earlier notification of it
 * entered (an orphan's, fallen back from a parent that ended, is the
 * session's first sign of it); and the agent's transcript shows the
 * hand-back contract on, so the placeholder is the engine's. Any lookup
 * that fails or cannot tell answers false.
 */
async function isRepeat($: EngineInterface, state: State, { taskId, worktree }: Interim): Promise<boolean> {
  if (worktree !== undefined && !state.told.has(`${taskId}\n${worktree}`)) {
    return false
  }
  if (state.subagents === undefined || !/^[\w-]+$/.test(taskId)) {
    return false
  }
  if (!state.told.has(taskId)) {
    const agent = (await $.agent.list()).find((listed) => listed.id === taskId)
    if (agent === undefined || agent.parentId !== undefined) {
      return false
    }
  }
  const search = await $.process.run(searchArgs(`${state.subagents}/agent-${taskId}.jsonl`), { timeoutMs: 10_000 })
  return search.exitCode === 0 && !search.isStdoutTruncated && handsBack(search.stdout)
}

/**
 * Drops, before it enters the session, an interim notification whose result
 * is the engine's waiting placeholder and that tells the session nothing new:
 * otherwise each one wakes the session for a turn with nothing to act on.
 * The first notification to carry a worktree passes, since the launch never
 * said where an isolated agent's work lives, and so does an orphan's first.
 * Everything else passes as it came, and so does any notification a check
 * errs on.
 */
export function registerInterim(on: On) {
  const state: State = { told: new Set() }

  on('classic.SessionStart', { transcript_path: /^/ }, async (_$, e, next) => {
    state.subagents = subagentsDir(e.transcript_path)
    return next(e)
  })

  on('prompt.submit', { origin: { kind: 'task-notification' } }, async ($, e, next) => {
    const interim = readInterim(e.text)
    if (interim === undefined) {
      return next(e)
    }
    let isDropped = false
    try {
      isDropped = await isRepeat($, state, interim)
    } catch (error) {
      $.ui.log(`interim: a check failed (${String(error)}); the notification passes`, { to: 'debug' })
    }
    if (isDropped) {
      return { drop: 'interim agent notification: its work is still running' }
    }
    const passed = await next(e)
    if (passed.drop === undefined) {
      state.told.add(interim.taskId)
      if (interim.worktree !== undefined) {
        state.told.add(`${interim.taskId}\n${interim.worktree}`)
      }
    }
    return passed
  })
}
