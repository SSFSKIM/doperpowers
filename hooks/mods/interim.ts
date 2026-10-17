import type { EngineInterface, On } from 'claude-code'

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
  '(?:\\n<output-file>(?<outputFile>[^<\\n]*)</output-file>)?',
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
  /**
   * The agent's `.output`, a link to its transcript; absent where the engine
   * leaves it out (an unreadable output, saved web-fetch files).
   */
  outputFile?: string
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
  return {
    taskId: groups.taskId,
    ...(groups.outputFile !== undefined && { outputFile: groups.outputFile }),
    ...(groups.worktree !== undefined && { worktree: groups.worktree }),
  }
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

const NOTICE = /<task-notification>\n<task-id>([^<\n]*)<\/task-id>\n[\s\S]*?<\/task-notification>/g

/**
 * Whether the conversation as the model reads it holds an earlier
 * notification of the task, carrying the worktree when one is named: in a
 * user message's text, where a notification that started a turn and one
 * that came in mid-turn (rendered under the engine's system-notification
 * frame) both land. A tool result or an assistant message quoting one does
 * not count.
 */
export function holds(messages: readonly { role: string; content: unknown }[], taskId: string, worktree?: string): boolean {
  for (const { role, content } of messages) {
    if (role !== 'user') {
      continue
    }
    const texts = typeof content === 'string'
      ? [content]
      : Array.isArray(content)
        ? content.flatMap((block) => (block?.type === 'text' && typeof block.text === 'string' ? [block.text as string] : []))
        : []
    for (const text of texts) {
      for (const [notice, id] of text.matchAll(NOTICE)) {
        if (id === taskId && (worktree === undefined || notice.includes(worktree))) {
          return true
        }
      }
    }
  }
  return false
}

/**
 * Whether the notification tells the session nothing its conversation does
 * not already hold, and its placeholder is the engine's. The session knows
 * the agent when its own loop spawned it; an orphan's notification, fallen
 * back from a parent that ended, is the session's first sign of it, so an
 * orphan's repeats need an earlier notification of it in the conversation,
 * and a worktree's need one carrying that worktree. The conversation is read
 * as it stands (`$.session.messages({ as: "api" })`, past a rewind and from
 * the last compaction on), so a notice rewound or summarized away, or one a
 * hook beneath answered for or rewrote, is not there. The placeholder is the
 * engine's when the agent's transcript, which its `<output-file>` links to,
 * shows the hand-back contract on. Any lookup that fails or cannot tell
 * answers false.
 */
async function isRepeat($: EngineInterface, { taskId, outputFile, worktree }: Interim): Promise<boolean> {
  if (outputFile === undefined) {
    return false
  }
  const agent = (await $.agent.list()).find((listed) => listed.id === taskId)
  if (agent === undefined) {
    return false
  }
  if (worktree !== undefined || agent.parentId !== undefined) {
    const conversation = await $.session.messages({ as: 'api' })
    if (!Array.isArray(conversation) || !holds(conversation, taskId, worktree)) {
      return false
    }
  }
  const transcript = (await $.fs.stat(outputFile, { resolve: true })).realPath
  if (transcript === undefined || !transcript.endsWith(`/agent-${taskId}.jsonl`)) {
    return false
  }
  const search = await $.process.run(searchArgs(transcript), { timeoutMs: 10_000 })
  return search.exitCode === 0 && !search.isStdoutTruncated && handsBack(search.stdout)
}

/**
 * Drops, before it enters the session, an interim notification whose result
 * is the engine's waiting placeholder and that tells the session nothing its
 * conversation does not hold: otherwise each one wakes the session for a
 * turn with nothing to act on. The first notification to carry a worktree
 * passes, since the launch never said where an isolated agent's work lives,
 * and so does an orphan's first. Everything else passes as it came, and so
 * does any notification a check errs on.
 */
export function registerInterim(on: On) {
  on('prompt.submit', { origin: { kind: 'task-notification' } }, async ($, e, next) => {
    const interim = readInterim(e.text)
    if (interim === undefined) {
      return next(e)
    }
    let isDropped = false
    try {
      isDropped = await isRepeat($, interim)
    } catch (error) {
      $.ui.log(`interim: a check failed (${String(error)}); the notification passes`, { to: 'debug' })
    }
    return isDropped ? { drop: 'interim agent notification: its work is still running' } : next(e)
  })
}
