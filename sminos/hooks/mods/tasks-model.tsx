import { simpleCommands } from './backticks'
import type { LexedWord } from './backticks'

/**
 * The tasks' mod's parts that take no `$` (tasks.tsx holds the hooks): the
 * subagent's attribution, the reading of `sminos task status`, and the texts
 * the human is shown. Child B1 of docs/doperpowers/specs/2026-11-27-task-board-design.md,
 * execution document docs/doperpowers/plans/2026-11-27-task-board-b1.md, §6 and M4.
 *
 * **The attribution** (the composite's D2, binding on the flag's names and
 * place). A subagent's shell carries its parent's session id and no agent id,
 * so the store cannot tell which subagent assigned a task; the engine tells a
 * `tool.call` hook (`e.agentId`). `attribute` puts
 * `--asker-agent <id> --asker-name <word>` directly after the verb of each
 * simple command that assigns: `task assign-human`, or `sminos task assign`
 * (`sminos.py` too). Read with the backtick guard's lexer (`simpleCommands`),
 * never matched as text, and only where the verb is a literal word of the
 * command itself, so the flag lands in the bytes that run:
 *
 * - The command word is the first after the reserved words that may begin a
 *   command (`if`, `then`, `do`, `time` with its `-p`, `!`, …) and any
 *   assignments, named by its last path part (`~/bin/task` counts). A command
 *   reached through another (`env task …`, `ssh …`) is no command word and is
 *   left as written.
 * - Left unchanged: a verb with a quote, escape, expansion or continuation in
 *   it; a command inside `$( … )` or in a heredoc's body; a command the lexer
 *   gives up on; a simple command that already carries `--asker-agent` (or a
 *   prefix argparse would take for it: an agent that writes the flag is
 *   believed); an id that is not whole `[A-Za-z0-9_.@-]{1,128}` (D2), or that
 *   begins with `-`, which the command's parser would read as an option.
 * - The name is reduced (`reducedName`): any run outside `[A-Za-z0-9_.-]` one
 *   `-`, none at either end, at most 64, left out when nothing remains. It is
 *   shown to the human on the board and put in no message to an agent (D5).
 *
 * Insertions are made from the command's end backwards, so the places read
 * before them stay true.
 */

/** D2's pattern for an agent id the store keeps. */
export const AGENT_ID = /^[A-Za-z0-9_.@-]{1,128}$/

/** Words that may stand before a command word: the shell's reserved words that begin a command. */
const LEADING = new Set(['!', 'time', 'if', 'then', 'elif', 'else', 'do', 'while', 'until', '{'])
const NAME_ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*\+?=/
const FLAG = '--asker-agent'
/** The shortest prefix the assign's parser takes for `--asker-agent` (`--asker-` is also `--asker-name`'s). */
const FLAG_PREFIX = '--asker-a'

/** The name as the board keeps it, or undefined when nothing of it remains. */
export function reducedName(name: string | undefined): string | undefined {
  const reduced = (name ?? '')
    .replace(/[^A-Za-z0-9_.-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
  return reduced === '' ? undefined : reduced
}

const literal = (w: LexedWord | undefined, text: string) => w !== undefined && w.span !== undefined && w.text === text

/** Whether a word is the flag, or a prefix of it the parser would resolve to it, with or without `=value`. */
const isFlag = (w: LexedWord) => {
  const name = w.text.split('=')[0] ?? ''
  return name.length >= FLAG_PREFIX.length && FLAG.startsWith(name)
}

/** Where the flag goes in one simple command: the end of its verb, or undefined. */
function verbEnd(words: readonly LexedWord[]): number | undefined {
  const args = words.filter((w) => !w.redirect)
  let i = 0
  while (i < args.length && !args[i]!.quoted && LEADING.has(args[i]!.text)) {
    i += args[i]!.text === 'time' && literal(args[i + 1], '-p') ? 2 : 1
  }
  while (i < args.length && NAME_ASSIGNMENT.test(args[i]!.text)) i++
  const head = args[i]
  if (head === undefined) return undefined
  const name = head.text.slice(head.text.lastIndexOf('/') + 1)
  let verb: number
  if (name === 'task' && literal(args[i + 1], 'assign-human')) {
    verb = i + 1
  } else if ((name === 'sminos' || name === 'sminos.py') && literal(args[i + 1], 'task') && literal(args[i + 2], 'assign')) {
    verb = i + 2
  } else {
    return undefined
  }
  return args.slice(verb + 1).some(isFlag) ? undefined : args[verb]!.span![1]
}

/** The command with the attribution after each assigning verb, or undefined for no change. */
export function attribute(command: string, agentId: string, name: string | undefined): string | undefined {
  if (!AGENT_ID.test(agentId) || agentId.startsWith('-') || !command.includes('assign')) return undefined
  const commands = simpleCommands(command)
  if (commands === undefined) return undefined
  const ends = commands.map((c) => verbEnd(c.words)).filter((end): end is number => end !== undefined)
  if (ends.length === 0) return undefined
  const word = reducedName(name)
  const flag = ` ${FLAG} ${agentId}${word === undefined ? '' : ` --asker-name ${word}`}`
  let out = command
  for (const end of ends.sort((a, b) => b - a)) out = out.slice(0, end) + flag + out.slice(end)
  return out
}

// ------------------------------------------------------------------ what the mod reads (§4)

/** `sminos task status --session <id> --json`, as the mod keeps it. */
export type Status = {
  seq: number
  /** This session's target's open tasks. */
  open: { count: number; blocking: number }
  /** The open blocking tasks this session assigned, newest first (at most 50). */
  mine: { id: string; title: string; born: number }[]
  /** A live surface's board address, or null. */
  board: { url: string } | null
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const isCount = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= 0
const TASK_ID = /^t[1-9][0-9]*$/

/** The command's answer, or undefined for anything that is not one. */
export function statusOf(stdout: string): Status | undefined {
  let v: unknown
  try {
    v = JSON.parse(stdout)
  } catch {
    return undefined
  }
  if (!isRecord(v) || v.v !== 1 || !isCount(v.seq) || !isRecord(v.open) || !isCount(v.open.count) || !isCount(v.open.blocking) || !Array.isArray(v.mine)) {
    return undefined
  }
  const mine: Status['mine'] = []
  for (const m of v.mine) {
    if (!isRecord(m) || typeof m.id !== 'string' || !TASK_ID.test(m.id) || typeof m.title !== 'string' || !isCount(m.born)) return undefined
    mine.push({ id: m.id, title: m.title, born: m.born })
  }
  const board = v.board
  if (board !== null && !(isRecord(board) && typeof board.url === 'string')) return undefined
  return { seq: v.seq, open: { count: v.open.count, blocking: v.open.blocking }, mine, board: board === null ? null : { url: board.url as string } }
}

/** Text from a store or a registration, on one line: controls out, any run of space one space. */
const oneLine = (text: string) =>
  text
    .replace(/[\t\n\r\f\v]+/g, ' ')
    .replace(/[\u0000-\u001f\u007f-\u009f]/g, '')
    .replace(/ {2,}/g, ' ')
    .trim()

/** The line above the prompt (D8): `2 tasks for the human (1 blocking) · <the board>`; none with nothing open. */
export function taskBandLine(open: { count: number; blocking: number }, board: { url: string } | null): string | undefined {
  if (open.count === 0) return undefined
  const blocking = open.blocking > 0 ? ` (${open.blocking} blocking)` : ''
  const address = board === null ? '' : oneLine(board.url)
  return `${open.count} task${open.count === 1 ? '' : 's'} for the human${blocking} · ${address === '' ? 'sminos task list' : address}`
}

/** The machine's notification for a new blocking task (D8), shown to the human and to no agent. */
export function notification(title: string): string {
  return `A blocking task for you: ${oneLine(title)}`
}
