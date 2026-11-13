import type { EngineInterface, On, SessionAppendInput } from 'claude-code'

import type { FoldRun, Folds, OpenFold, OpenFoldLast } from '../../types/to-human'
import { MESSAGE_TOOL, isMadeUp } from './message'
import type { PromptRowProps, View } from './to-human'
import { isApiError, isRead, isSpawn, keyOf, parse, promptRow } from './to-human'

/**
 * The run tracker: what a fold's button says before it is opened. The view
 * learns of a row only when the row draws, and in a fullscreen terminal rows
 * outside the window never draw, so it can tell neither what a run holds nor
 * when it closed. The tracker follows the main conversation's rows as the
 * engine keeps them instead, sorts each by the view's own rules (`isRead`,
 * `parse`, `promptRow`, `isApiError`) into the runs of working record between
 * the rows the person reads, and publishes each run's bounds and live line
 * in `$.state` (`types/to-human.d.ts`), where the view's buttons read them.
 * The two meet only at a row's place in the transcript (`View.place`). Each
 * run that closes, and the open run at a turn's end, is summarized in one
 * line by a model call over its digest (`LABEL_SYSTEM`), kept in the
 * session's file so a resume shows it again.
 */

/** A row as the main conversation keeps it: what `session.append` hands a hook, and the row as stored. */
export type KeptRow = Pick<SessionAppendInput, 'door' | 'origin' | 'uuid' | 'agentId' | 'message'>

/**
 * What one kept row does to the runs, block by block in order: a note, a call
 * or a delivery joins the open run (a call's row known by its call's id, any
 * other by the row's), a result joins its call's run wherever that stands,
 * and a read row closes the open run. `end` is the main conversation's
 * turn's end, which no row stands for.
 */
export type Step =
  | { kind: 'note'; id: string; text: string }
  | { kind: 'call'; id: string; tool: string; input: unknown }
  | { kind: 'delivery'; id: string; text: string }
  | { kind: 'result'; call: string; text: string; isError: boolean }
  | { kind: 'read'; id: string }
  | { kind: 'end' }

const textOf = (content: SessionAppendInput['message']['content']) =>
  content.flatMap((block) => (block.type === 'text' && typeof block.text === 'string' ? [block.text] : [])).join('\n')

/** A tool result's content as text: its texts, one to a line, any other block by its type. */
function resultText(content: unknown): string {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''
  return content
    .flatMap((block: unknown) => {
      if (typeof block !== 'object' || block === null) return []
      const { type, text } = block as { type?: unknown; text?: unknown }
      return [type === 'text' ? (typeof text === 'string' ? text : '') : `[${String(type)}]`]
    })
    .join('\n')
}

/**
 * The background task a kept prompt reports on, from the engine's
 * `<task-notification>` that opens its text: what the drawn row carries as
 * `task`, which the kept row does not.
 */
function taskOf(text: string): PromptRowProps['task'] {
  const body = /^\s*<task-notification>([\s\S]*?)(?:<\/task-notification>|$)/.exec(text)?.[1]
  if (body === undefined) return undefined
  const field = (name: string) => new RegExp(`<${name}>([^<]*)</${name}>`).exec(body)?.[1]?.trim()
  const [id, toolUseId, status] = [field('task-id'), field('tool-use-id'), field('status')]
  return { ...(id !== undefined && { id }), ...(toolUseId !== undefined && { toolUseId }), ...(status !== undefined && { status }) }
}

/**
 * A kept prompt as `promptRow` reads a drawn one: the drawing's `task` and
 * `from` rebuilt from the row. A sender is present where the row is not the
 * person's typing: a channel's message (the engine gives its drawing the
 * sender, and `promptRow` reads a `channel` origin without one as the
 * person's), or a row the engine marks `isMeta`, a user-side row the person
 * does not see as typed (a subagent's hand-back).
 */
function promptStep(row: KeptRow, spawns: ReadonlySet<string>): Step {
  const text = textOf(row.message.content)
  const task = taskOf(text)
  const from = row.origin.kind === 'channel' ? { name: row.origin.server } : row.message.isMeta === true ? { name: row.origin.kind } : undefined
  const props: PromptRowProps = { origin: { kind: row.origin.kind } as PromptRowProps['origin'], text, ...(task !== undefined && { task }), ...(from !== undefined && { from }) }
  return promptRow(props, spawns) === 'record' ? { kind: 'delivery', id: row.uuid, text } : { kind: 'read', id: row.uuid }
}

function responseSteps(row: KeptRow, spawns: Set<string>): Step[] {
  if (isApiError(row.origin, row.message)) return [{ kind: 'read', id: row.uuid }]
  // The response the message mod makes up after a final message stands for no text of the model's.
  if (isMadeUp(row.uuid, textOf(row.message.content))) return []
  return row.message.content.flatMap((block): Step[] => {
    if (block.type === 'text' && typeof block.text === 'string') {
      if (block.text.trim() === '') return []
      const parsed = parse(block.text)
      const note: Step = { kind: 'note', id: row.uuid, text: block.text }
      // A mixed message is read, and opens the next run with its own record, as the view draws its button on it.
      return parsed.spans.length === 0 ? [note] : parsed.hasRecord ? [{ kind: 'read', id: row.uuid }, note] : [{ kind: 'read', id: row.uuid }]
    }
    if (block.type === 'tool_use' && typeof block.id === 'string' && typeof block.name === 'string') {
      if (!isRead(block.name)) return [{ kind: 'call', id: block.id, tool: block.name, input: block.input }]
      if (isSpawn(block.name)) spawns.add(block.id)
      return [{ kind: 'read', id: block.id }]
    }
    return []
  })
}

/**
 * What a kept row does ("What each kept row does" in
 * docs/doperpowers/specs/2026-11-12-fold-summaries-design.md). A
 * subagent's rows, thinking, hook context, notices, commands, attachments, a
 * row a tool hands over beside its result, a queue record and a plugin's own
 * note do nothing. `spawns` gathers the ids of the spawns the report shows,
 * whose failure notifications it shows too.
 */
export function stepsOf(row: KeptRow, spawns: Set<string>): Step[] {
  if (row.agentId !== undefined) return []
  switch (row.door) {
    case 'response':
      return responseSteps(row, spawns)
    case 'tool-result':
      return row.message.content.flatMap((block): Step[] =>
        block.type === 'tool_result' && typeof block.tool_use_id === 'string'
          ? [{ kind: 'result', call: block.tool_use_id, text: resultText(block.content), isError: block.is_error === true }]
          : [],
      )
    case 'prompt':
    case 'delivery':
      return [promptStep(row, spawns)]
    case 'compaction':
      return [{ kind: 'read', id: row.uuid }]
    default:
      return []
  }
}

/** How long a live line runs before it is cut. */
const LINE_MAX = 120

/** One line: newlines become spaces, and past `LINE_MAX` characters it is cut with `…`, between code points. */
function oneLine(text: string): string {
  const chars = Array.from(text.replace(/\s*[\r\n]+\s*/g, ' ').trim())
  return chars.length > LINE_MAX ? `${chars.slice(0, LINE_MAX - 1).join('')}…` : chars.join('')
}

const baseName = (path: string) => path.split(/[/\\]/).filter((part) => part !== '').at(-1) ?? path

/** The call's line by its tool, or undefined where the input lacks what the line is made of. */
function lineFor(tool: string, field: (name: string) => string | undefined): string | undefined {
  switch (tool) {
    case 'Bash':
      return field('description') ?? field('command')?.trim().split('\n')[0]
    case 'Read':
    case 'Edit':
    case 'Write': {
      const path = field('file_path')
      return path === undefined ? undefined : `${tool} ${baseName(path)}`
    }
    case 'NotebookEdit': {
      const path = field('notebook_path')
      return path === undefined ? undefined : `Edit ${baseName(path)}`
    }
    case 'Grep':
    case 'Glob': {
      const pattern = field('pattern')
      return pattern === undefined ? undefined : `Search "${pattern}"`
    }
    case 'SendMessage': {
      const [to, summary] = [field('to'), field('summary')]
      return to === undefined ? undefined : summary === undefined ? `Message to ${to}` : `Message to ${to}: ${summary}`
    }
    case 'Skill': {
      const skill = field('skill')
      return skill === undefined ? undefined : `Skill ${skill}`
    }
    case 'ToolSearch': {
      const query = field('query')
      return query === undefined ? undefined : `Tool search "${query}"`
    }
  }
  const mcp = /^mcp__(.+?)__(.+)$/.exec(tool)
  return mcp === null ? undefined : `${mcp[1]}: ${mcp[2]}`
}

/**
 * One tool call as one line (the live line's table), built from the call's
 * name and input, since a hook gets those and not the line the engine draws.
 */
export function lineOf(tool: string, input: unknown): string {
  const field = (name: string) => {
    const value = typeof input === 'object' && input !== null ? (input as Record<string, unknown>)[name] : undefined
    return typeof value === 'string' && value.trim() !== '' ? value : undefined
  }
  return oneLine(lineFor(tool, field) ?? tool)
}

/** The summary: the reply's first non-empty line, trimmed and cut at 120 characters; undefined for none. */
export function summaryOf(reply: string): string | undefined {
  const line = reply.split(/\r?\n/).map((part) => part.trim()).find((part) => part !== '')
  return line === undefined ? undefined : oneLine(line)
}

/**
 * The system prompt of the summary call: what the person sees in place of a
 * folded run, in plain words (the wording the human partner chose over a
 * specific and a terse one on the same twelve runs).
 */
export const LABEL_SYSTEM = [
  'You label folded stretches of a coding agent\'s working record. The person supervising the agent sees your label in place of the stretch and decides from it whether to open the stretch. They have not read the stretch and do not know the names the agent made up while working.',
  'You are given one stretch: the agent\'s own notes (NOTE), its tool calls (CALL), their results cut to their ends (RESULT), and messages delivered to it from subagents, jobs or other sessions (DELIVERED).',
  'Write one line of at most 90 characters, in the past tense with no subject: what was done and what it came to, in plain words. Keep pull request and issue numbers and the counts that matter (tests passed, files changed); leave out commit hashes, run ids and the agent\'s own working labels, saying what the thing is instead. Write in the language the agent\'s notes are written in, and in English when there are none. State nothing the record does not show. Answer with the line alone.',
].join('\n\n')

// The digest's cuts, in characters: each part's as it is added, the whole's at the end.
const NOTE_MAX = 1500
const COMMAND_MAX = 600
const INPUT_MAX = 400
const DELIVERY_MAX = 600
const RESULT_HEAD = 600
const RESULT_TAIL = 400
/** Past this the digest keeps its start, to 40% of it, and its end, to 60%: about 30k tokens, under the 100k where Haiku's price steps up. */
const DIGEST_MAX = 60_000

const isHighSurrogate = (unit: string | undefined) => unit !== undefined && /[\uD800-\uDBFF]/.test(unit)
const isLowSurrogate = (unit: string | undefined) => unit !== undefined && /[\uDC00-\uDFFF]/.test(unit)
/** The first `n` units of `text`, never half a pair. */
const headOf = (text: string, n: number) => text.slice(0, isHighSurrogate(text[n - 1]) ? n - 1 : n)
/** The last `n` units of `text`, never half a pair. */
const tailOf = (text: string, n: number) => text.slice(text.length - n + (isLowSurrogate(text[text.length - n]) ? 1 : 0))

/** `text` trimmed, and past `max` characters cut, saying how many more there were. */
function clip(text: string, max: number): string {
  const whole = text.trim()
  return whole.length <= max ? whole : `${headOf(whole, max)} …[${whole.length - max} more chars]`
}

/** `text` trimmed, and past `head + tail` characters cut to its ends: test and build output puts its verdict last. */
function clipEnds(text: string, head: number, tail: number): string {
  const whole = text.trim()
  return whole.length <= head + tail ? whole : `${headOf(whole, head)}\n…[${whole.length - head - tail} chars cut]…\n${tailOf(whole, tail)}`
}

/** A call as the digest has it: a command with its description, a file by its path, anything else by its input. */
function callPart(tool: string, input: unknown): string {
  const fields = typeof input === 'object' && input !== null ? (input as Record<string, unknown>) : {}
  const field = (name: string) => (typeof fields[name] === 'string' ? (fields[name] as string) : undefined)
  if (tool === 'Bash') {
    const description = field('description')?.trim()
    return `CALL Bash${description ? ` — ${description}` : ''}\n$ ${clip(field('command') ?? '', COMMAND_MAX)}`
  }
  const path = field('file_path') ?? field('path') ?? field('notebook_path')
  if (path !== undefined) {
    const pattern = field('pattern')
    return `CALL ${tool} ${path}${pattern === undefined ? '' : ` pattern=${JSON.stringify(pattern)}`}`
  }
  return `CALL ${tool} ${clip(JSON.stringify(input ?? {}), INPUT_MAX)}`
}

/** What stands between a digest's parts. */
const SEPARATOR = '\n\n'
/** The line that stands for the parts a capped digest left out. */
const omission = (count: number) => `…[${count} rows of the run omitted here]…`

/**
 * A run's digest as it grows, measured as the text it joins to: its parts in
 * order while that fits the cap; past it, the parts that fit 40% of it from
 * the start (`head` of them), and those that fit what is left of the cap
 * from the end once the omission line and its separators are counted, the
 * ones between dropped and counted. `size` is the joined length of the parts
 * after the head (of them all while there is none), `headSize` the head's.
 */
type Digest = { parts: string[]; size: number; head?: number; headSize: number; omitted: number }

const newDigest = (): Digest => ({ parts: [], size: 0, headSize: 0, omitted: 0 })

function addPart(digest: Digest, part: string) {
  digest.size += (digest.parts.length > (digest.head ?? 0) ? SEPARATOR.length : 0) + part.length
  digest.parts.push(part)
  if (digest.head === undefined) {
    if (digest.size <= DIGEST_MAX) return
    let head = 0
    while (head < digest.parts.length) {
      const next = digest.headSize + (head > 0 ? SEPARATOR.length : 0) + digest.parts[head]!.length
      if (next > DIGEST_MAX * 0.4) break
      digest.headSize = next
      head += 1
    }
    digest.head = head
    digest.size = digest.parts.slice(head).join(SEPARATOR).length
  }
  const room = () => DIGEST_MAX * 0.6 - 2 * SEPARATOR.length - omission(digest.omitted).length
  while (digest.parts.length > digest.head && digest.size > room()) {
    const dropped = digest.parts.splice(digest.head, 1)[0]!
    digest.size -= dropped.length + (digest.parts.length > digest.head ? SEPARATOR.length : 0)
    digest.omitted += 1
  }
}

const digestText = (digest: Digest) =>
  (digest.head === undefined
    ? digest.parts
    : [...digest.parts.slice(0, digest.head), omission(digest.omitted), ...digest.parts.slice(digest.head)]
  ).join(SEPARATOR)

/** A run as the tracker holds it. */
type Run = {
  first: string
  /** The newest row that joined; once the run is closed, its last. */
  last: string
  line?: string
  summary?: string
  /** The last row its summary covered: the open run's bound in the session's file. */
  covered?: string
  isLive: boolean
  /** Its calls whose results have not been kept. */
  running: Set<string>
  /** The tracker saw every row of it: false for a run a module before this one held. */
  isWhole: boolean
  /** Bumped whenever a row or a result joins it: a reply asked for at another is stale. */
  generation: number
  /** The generation its summary was last asked for at: one attempt each. */
  asked?: number
  digest: Digest
}

/** A summary to ask for: the run, the generation it was asked at, and what the model reads. */
export type Ask = { run: Run; generation: number; digest: string }

/** The tracker's memory, the authority for what it publishes. */
export type Tracker = {
  /** The closed runs, oldest first. */
  closed: Run[]
  open: Run | null
  /** The run each call stands in, until its result is kept. */
  runOfCall: Map<string, Run>
  /** The spawns the report shows (`stepsOf`). */
  spawns: Set<string>
}

export const newTracker = (): Tracker => ({ closed: [], open: null, runOfCall: new Map(), spawns: new Set() })

const newRun = (id: string): Run => ({ first: id, last: id, isLive: true, running: new Set(), isWhole: true, generation: 0, digest: newDigest() })

/** A run's summary settled, or its call failed or was skipped: no longer live, its live line let go, any summary it had kept. */
function settle(run: Run, summary: string | undefined) {
  if (summary !== undefined) {
    run.summary = summary
    run.covered = run.last
  }
  run.isLive = false
  delete run.line
}

/**
 * A run due its summary: closed with every call's result kept, or at a
 * turn's end. Asked for once a generation, and only of a run held whole in a
 * session that asks; any other settles at once. Asked, it stays live until
 * the reply settles it.
 */
function due(run: Run, isAsking: boolean, asks: Ask[]) {
  if (run.asked === run.generation) return
  if (!isAsking || !run.isWhole) {
    settle(run, undefined)
    return
  }
  run.asked = run.generation
  run.isLive = true
  asks.push({ run, generation: run.generation, digest: digestText(run.digest) })
}

const join = (run: Run, part: string) => {
  run.generation += 1
  addPart(run.digest, part)
}

/**
 * Takes the steps of one kept row, in order; the summaries they make due
 * where `isAsking`. A run closes at a read row and is due once its calls'
 * results are kept; at a turn's end a closed run still waiting on one is due
 * as it stands, and so is the open run if rows joined it since its last
 * summary, which it stays.
 */
export function follow(tracker: Tracker, steps: readonly Step[], isAsking = false): Ask[] {
  const asks: Ask[] = []
  for (const step of steps) {
    if (step.kind === 'result') {
      const run = tracker.runOfCall.get(step.call)
      if (run === undefined) continue
      tracker.runOfCall.delete(step.call)
      run.running.delete(step.call)
      join(run, `RESULT ${step.isError ? '(error) ' : ''}${clipEnds(step.text, RESULT_HEAD, RESULT_TAIL)}`)
      // Live again, open or closed: a closed run is asked for when its last result is kept or at the next turn's end.
      run.isLive = true
      if (run !== tracker.open && run.running.size === 0) due(run, isAsking, asks)
    } else if (step.kind === 'read') {
      const run = tracker.open
      if (run === null) continue
      tracker.open = null
      tracker.closed.push(run)
      if (run.running.size === 0) due(run, isAsking, asks)
    } else if (step.kind === 'end') {
      for (const run of tracker.closed) {
        if (run.isLive && run.running.size > 0) due(run, isAsking, asks)
      }
      if (tracker.open?.isLive) due(tracker.open, isAsking, asks)
    } else {
      const run = (tracker.open ??= newRun(step.id))
      run.last = step.id
      run.isLive = true
      if (step.kind === 'call') {
        run.line = lineOf(step.tool, step.input)
        run.running.add(step.id)
        tracker.runOfCall.set(step.id, run)
        join(run, callPart(step.tool, step.input))
      } else {
        join(run, step.kind === 'note' ? `NOTE ${clip(step.text, NOTE_MAX)}` : `DELIVERED ${clip(step.text, DELIVERY_MAX)}`)
      }
    }
  }
  return asks
}

/** A run as published; the open run's newest row goes under `foldLast` instead, which no drawing reads. */
const shown = (run: Run, isClosed: boolean): FoldRun => ({
  first: run.first,
  ...(isClosed && { last: run.last }),
  ...(run.line !== undefined && { line: run.line }),
  ...(run.summary !== undefined && { summary: run.summary }),
  ...(run.isLive && { isLive: true as const }),
})

/** What the tracker publishes: the closed runs (`folds`), the open one (`fold`) and its newest row (`foldLast`). */
export const published = (tracker: Tracker): { folds: Folds; fold: OpenFold; foldLast: OpenFoldLast } => ({
  folds: { shape: 1, runs: tracker.closed.map((run) => shown(run, true)) },
  fold: tracker.open === null ? null : shown(tracker.open, false),
  foldLast: tracker.open?.last ?? null,
})

/** The session's file: each run with a summary by its first row, the last row it holds and the summary. */
export type StoredFolds = { shape: 1; runs: [string, string, string][] }

/** What the session's file keeps: every run with a summary, the open run's bounded by the last row its summary covered. */
export function stored(tracker: Tracker): StoredFolds {
  const runs = tracker.closed.flatMap((run): [string, string, string][] => (run.summary === undefined ? [] : [[run.first, run.last, run.summary]]))
  const open = tracker.open
  if (open?.summary !== undefined) runs.push([open.first, open.covered ?? open.last, open.summary])
  return { shape: 1, runs }
}

/** A session's file read back as closed runs, or undefined when it is not one. */
export function storedRuns(text: string): FoldRun[] | undefined {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    return undefined
  }
  const { shape, runs } = (typeof value === 'object' && value !== null ? value : {}) as { shape?: unknown; runs?: unknown }
  if (shape !== 1 || !Array.isArray(runs)) return undefined
  return runs.flatMap((run: unknown) =>
    Array.isArray(run) && run.length === 3 && run.every((part) => typeof part === 'string') ? [{ first: run[0] as string, last: run[1] as string, summary: run[2] as string }] : [],
  )
}

const isFoldRun = (value: unknown): value is FoldRun =>
  typeof value === 'object' && value !== null && typeof (value as { first?: unknown }).first === 'string'

const held = (run: FoldRun, last: unknown = run.last): Run => {
  const bound = typeof last === 'string' ? last : run.first
  return {
    first: run.first,
    last: bound,
    ...(typeof run.line === 'string' && { line: run.line }),
    ...(typeof run.summary === 'string' && { summary: run.summary, covered: bound }),
    isLive: run.isLive === true,
    running: new Set(),
    isWhole: false,
    generation: 0,
    digest: newDigest(),
  }
}

/**
 * Takes up the runs a module before this one published (a reload of the
 * plugin's code loses the module's memory; `$.state` outlives it), or a
 * session's file. The open run goes on, held not whole: its calls' results
 * are unknown here, and so is what it held; its newest row (`openLast`)
 * bounds it when it closes, and its summary in the file. A closed run still
 * live was waiting on something that died with that module, so it settles
 * with what it had.
 */
export function takeUp(tracker: Tracker, folds: Folds | undefined, open: OpenFold | undefined, openLast: OpenFoldLast | undefined) {
  const runs = folds?.shape === 1 && Array.isArray(folds.runs) ? folds.runs.filter(isFoldRun) : []
  tracker.closed = runs.map((run) => {
    const closed = held(run)
    if (closed.isLive) settle(closed, undefined)
    return closed
  })
  tracker.open = isFoldRun(open) ? held(open, openLast) : null
}

/** The label a run's button reads: the live line while it is live (else its summary), its summary once it is not. */
const labelFor = (run: FoldRun) => (run.isLive === true ? run.line ?? run.summary : run.summary)

/**
 * The text a fold's button reads for the run `rowId` stands in, or undefined
 * for `working record`: the open run's, if the row's place is at or after the
 * open run's first row's, else the closed run whose first and last rows'
 * places hold it. A row whose place, or whose run's bound's place, the view
 * does not know reads nothing (a place the view only guessed, for a row drawn
 * before it was kept, is not one). A group is known by its first call's id.
 * By place, so whichever row of a run draws its button finds the label.
 */
export function labelOf(folds: Folds | undefined, open: OpenFold | undefined, view: View, rowId: string): string | undefined {
  const at = view.place.get(keyOf(rowId))
  if (at === undefined) return undefined
  const from = open === null || open === undefined ? undefined : view.place.get(keyOf(open.first))
  if (open && from !== undefined && at >= from) return labelFor(open)
  const runs = folds?.runs ?? []
  for (let i = runs.length - 1; i >= 0; i -= 1) {
    const run = runs[i]!
    const [first, last] = [view.place.get(keyOf(run.first)), run.last === undefined ? undefined : view.place.get(keyOf(run.last))]
    if (first !== undefined && last !== undefined && first <= at && at <= last) return labelFor(run)
  }
  return undefined
}

const FOLDS = { plugin: 'to-human', key: 'folds' } as const
const OPEN = { plugin: 'to-human', key: 'fold' } as const
const OPEN_LAST = { plugin: 'to-human', key: 'foldLast' } as const

/** What a session reads once: the summaries' model, whether it is one nobody reads the report of here, and the files' folder. */
type Settings = { model: string; isQuiet: boolean; dir?: string }

/** What one registration of the tracker keeps between its hooks. */
type Following = {
  tracker: Tracker
  /** The rows' steps kept before the start-up read landed, in order; undefined once it has. */
  backlog: Step[][] | undefined
  loading?: Promise<void>
  /** Bumped by a clear, a resume or a fork: a read or a reply begun before one takes up nothing. */
  epoch: number
  /** The writes to `$.state`, one after another. */
  writes: Promise<void>
  /** What was last written under each key, as JSON. */
  written: { folds: string; fold: string; foldLast: string }
  /** The view's "a mark has been seen". */
  isOn: () => boolean
  /** The tracker has followed a kept mark: the view's condition, read where the row is kept rather than drawn. */
  hasKeptMark: boolean
  /** `session.start`'s: nobody reads a headless session's terminal. */
  isInteractive: boolean
  settings?: Settings
  reading?: Promise<Settings | undefined>
  /** The session's file, for the conversation it was found in. */
  file: Promise<string | undefined>
  /** The writes of the session's file, one after another. */
  fileWrites: Promise<void>
}

/**
 * Whether a run due its summary is asked for: a to-human reader (a mark the
 * view drew, or one the tracker followed, so the message that closes a
 * session's first run counts for that run though it has not drawn yet), at
 * this terminal, not MAWS's or a sminos internal fork's.
 */
const isAsking = (following: Following) =>
  (following.isOn() || following.hasKeptMark) && following.isInteractive && following.settings !== undefined && !following.settings.isQuiet

/** A kept response that is a mark, as the view reads a drawn one: a message-tool call, or text with a marked span. */
const isMark = (row: KeptRow) =>
  row.door === 'response' &&
  row.message.content.some(
    (block) =>
      (block.type === 'tool_use' && block.name === MESSAGE_TOOL) ||
      (block.type === 'text' && typeof block.text === 'string' && parse(block.text).spans.length > 0),
  )

/** Reads the settings once. */
function readSettings($: EngineInterface, following: Following): Promise<Settings | undefined> {
  following.reading ??= (async () => {
    try {
      const [model, maws, internal, configured, home] = await Promise.all([
        $.env.get('TO_HUMAN_FOLD_MODEL'),
        $.env.get('MAWS_NATIVE_TO_HUMAN'),
        $.env.get('SMNS_INTERNAL'),
        $.env.get('CLAUDE_CONFIG_DIR'),
        $.env.get('HOME'),
      ])
      const config = configured || (home ? `${home}/.claude` : undefined)
      following.settings = {
        model: model || 'haiku',
        isQuiet: (maws !== undefined && maws !== '') || internal !== undefined,
        ...(config !== undefined && { dir: `${config}/to-human/folds` }),
      }
      return following.settings
    } catch (error) {
      $.ui.log(`to-human: the folds' settings could not be read (${String(error)}); no summaries`, { to: 'debug' })
      return undefined
    }
  })()
  return following.reading
}

/** The file of the session `id` names (this one when undefined), under the configuration's `to-human/folds/`; undefined where there is no configuration directory. */
async function fileOf($: EngineInterface, following: Following, id: string | undefined): Promise<string | undefined> {
  try {
    const dir = (await readSettings($, following))?.dir
    return dir === undefined ? undefined : `${dir}/${id ?? (await $.session.id())}.json`
  } catch (error) {
    $.ui.log(`to-human: the session's folds file could not be named (${String(error)})`, { to: 'debug' })
    return undefined
  }
}

/** The runs a session's file holds, or undefined for none. */
async function readStored($: EngineInterface, path: string | undefined): Promise<FoldRun[] | undefined> {
  if (path === undefined) return undefined
  try {
    if (!(await $.fs.exists(path))) return undefined
    const runs = storedRuns(await $.fs.read(path))
    if (runs === undefined) $.ui.log(`to-human: ${path} holds no folds it can read`, { to: 'debug' })
    return runs
  } catch (error) {
    $.ui.log(`to-human: ${path} could not be read (${String(error)})`, { to: 'debug' })
    return undefined
  }
}

/** Removes the sessions' files older than 30 days (`$.fs` has no delete). */
async function prune($: EngineInterface, dir: string | undefined) {
  if (dir === undefined) return
  try {
    if (await $.fs.exists(dir)) await $.process.run(['find', dir, '-type', 'f', '-name', '*.json', '-mtime', '+30', '-delete'])
  } catch (error) {
    $.ui.log(`to-human: the old folds files could not be removed (${String(error)})`, { to: 'debug' })
  }
}

/**
 * Writes what changed of the tracker's runs, after any write before it, so
 * the writes land in order: `foldLast` first, then `folds` before `fold`, so
 * a run that closes is never in neither. Each `fold` write draws the fold
 * buttons again, so `fold` changes only with what a button reads.
 */
function publish($: EngineInterface, following: Following) {
  const { folds, fold, foldLast } = published(following.tracker)
  const now = { folds: JSON.stringify(folds), fold: JSON.stringify(fold), foldLast: JSON.stringify(foldLast) }
  const [isFolds, isFold, isLast] = [now.folds !== following.written.folds, now.fold !== following.written.fold, now.foldLast !== following.written.foldLast]
  if (!isFolds && !isFold && !isLast) return
  following.written = now
  following.writes = following.writes
    .then(async () => {
      if (isLast) await $.state.set(OPEN_LAST, foldLast)
      if (isFolds) await $.state.set(FOLDS, folds)
      if (isFold) await $.state.set(OPEN, fold)
    })
    .catch((error: unknown) => $.ui.log(`to-human: the folds could not be published (${String(error)})`, { to: 'debug' }))
}

/** Writes the session's file whole, from memory, after any write of it before. */
function keepFile($: EngineInterface, following: Following) {
  const text = `${JSON.stringify(stored(following.tracker))}\n`
  const file = following.file
  following.fileWrites = following.fileWrites
    .then(async () => {
      const path = await file
      if (path !== undefined) await $.fs.write(path, text)
    })
    .catch((error: unknown) => $.ui.log(`to-human: the folds could not be kept in the session's file (${String(error)})`, { to: 'debug' }))
}

/**
 * Asks the model for one run's summary, unawaited by any hook, and merges the
 * reply into memory by its run: dropped when the conversation changed (a
 * clear, a resume, a fork) or the run took a row since it was asked. A reply
 * unanswered or empty, or a call that throws, leaves the summary as it was:
 * one attempt, no retry.
 */
async function summarize($: EngineInterface, following: Following, ask: Ask) {
  const epoch = following.epoch
  let summary: string | undefined
  try {
    const reply = await $.model.complete({
      model: following.settings?.model ?? 'haiku',
      system: LABEL_SYSTEM,
      prompt: `<stretch>\n${ask.digest}\n</stretch>`,
      effort: 'high',
      maxTokens: 4000,
      timeoutMs: 30_000,
    })
    summary = reply.isAnswered ? summaryOf(reply.text) : undefined
    if (summary === undefined) {
      $.ui.log(`to-human: a fold's summary came back ${reply.isAnswered ? 'empty' : `unanswered (${reply.reason})`}`, { to: 'debug' })
    }
  } catch (error) {
    $.ui.log(`to-human: a fold's summary could not be asked for (${String(error)})`, { to: 'debug' })
  }
  if (epoch !== following.epoch || ask.run.generation !== ask.generation) return
  settle(ask.run, summary)
  publish($, following)
  if (summary !== undefined) keepFile($, following)
}

/** Follows steps, publishes what they changed, and asks for the summaries they made due. */
function apply($: EngineInterface, following: Following, waiting: readonly Step[][]) {
  const asks = waiting.flatMap((steps) => follow(following.tracker, steps, isAsking(following)))
  publish($, following)
  for (const ask of asks) void summarize($, following, ask)
}

/** Lets through the rows that waited for a read, unless the conversation changed since it began. */
function release($: EngineInterface, following: Following, epoch: number) {
  if (epoch !== following.epoch) return
  const waiting = following.backlog ?? []
  following.backlog = undefined
  apply($, following, waiting)
}

/**
 * Takes up what a module before this one published, once, then the rows
 * that waited for it. A new process, whose `$.state` holds none of the
 * tracker's keys, takes up its session's file instead, every run of it as a
 * closed one, and removes the files older than 30 days.
 */
function load($: EngineInterface, following: Following): Promise<void> {
  following.loading ??= (async () => {
    const at = following.epoch
    following.file = fileOf($, following, undefined)
    try {
      const [folds, open, openLast] = await Promise.all([$.state.get(FOLDS), $.state.get(OPEN), $.state.get(OPEN_LAST)])
      const isNew = folds.value === undefined && open.value === undefined && openLast.value === undefined
      const fromFile = isNew ? await readStored($, await following.file) : undefined
      if (isNew) void prune($, (await readSettings($, following))?.dir)
      if (at === following.epoch) {
        takeUp(following.tracker, fromFile === undefined ? folds.value : { shape: 1, runs: fromFile }, open.value, openLast.value)
        // Nothing kept reads as no runs, so a start over nothing writes nothing.
        following.written = {
          folds: JSON.stringify(folds.value ?? published(newTracker()).folds),
          fold: JSON.stringify(open.value ?? null),
          foldLast: JSON.stringify(openLast.value ?? null),
        }
      }
    } catch (error) {
      $.ui.log(`to-human: the folds a module before left could not be read (${String(error)}); they start over`, { to: 'debug' })
    } finally {
      await readSettings($, following)
      release($, following, at)
    }
  })()
  return following.loading
}

/** Follows one row's steps: at once, or after the read under way, in order. */
function track($: EngineInterface, following: Following, steps: Step[]) {
  if (steps.length === 0) return
  if (following.backlog !== undefined) {
    following.backlog.push(steps)
    void load($, following)
    return
  }
  apply($, following, [steps])
}

/**
 * Drops the runs of the conversation before and publishes that, then the
 * file of the session it now is, once the writes already queued have
 * landed (a switch back to a session whose summary is still being written
 * would read its file without that summary); the rows kept meanwhile wait.
 */
function reset($: EngineInterface, following: Following, sessionId: string | undefined) {
  following.epoch += 1
  const at = following.epoch
  following.tracker = newTracker()
  following.backlog = []
  publish($, following)
  const file = fileOf($, following, sessionId)
  following.file = file
  const written = following.fileWrites
  following.loading = (async () => {
    try {
      await written
      const runs = await readStored($, await file)
      if (runs !== undefined && at === following.epoch) takeUp(following.tracker, { shape: 1, runs }, null, null)
    } finally {
      release($, following, at)
    }
  })()
}

/**
 * Registers the tracker's hooks. `isOn` is the view's "a mark has been
 * seen": the live lines are published in every session the plugin loads in
 * (a few small writes), the summaries asked for only where the session
 * writes for a to-human reader (`isAsking`).
 *
 * Rows are followed in the order their appends resolve; those kept before
 * the start-up read of `$.state` landed wait for it. Nothing here holds or
 * fails a row's keeping: each hook hands the row on as it was stored, and no
 * hook awaits a summary.
 */
export function registerFolds(on: On, view: View, isOn: () => boolean) {
  const following: Following = {
    tracker: newTracker(),
    backlog: [],
    epoch: 0,
    writes: Promise.resolve(),
    written: { folds: '', fold: '', foldLast: '' },
    isOn,
    hasKeptMark: false,
    isInteractive: false,
    file: Promise.resolve(undefined),
    fileWrites: Promise.resolve(),
  }

  // Each load of the module raises this, the first and every reload.
  on('session.start', { cwd: /./ }, async ($, e, next) => {
    following.isInteractive = e.isInteractive
    void load($, following)
    return next(e)
  })

  on('session.append', { door: /^[a-z-]+$/ }, async ($, e, next) => {
    const stored = await next(e)
    if (e.agentId === undefined && stored.deny === undefined) {
      try {
        const row: KeptRow = { door: e.door, origin: e.origin, uuid: stored.uuid, message: stored.message }
        // Noted before its steps are followed, so the mark that closes a run counts for it, a row waiting for the start-up read too.
        if (isMark(row)) following.hasKeptMark = true
        track($, following, stepsOf(row, following.tracker.spawns))
      } catch (error) {
        // The row is kept whatever this hook makes of it; only its run is lost.
        $.ui.log(`to-human: a kept row could not be followed (${String(error)})`, { to: 'debug' })
      }
    }
    return stored
  })

  // The main conversation's turn's end: the open run is summarized if it took rows since its last summary.
  on('turn.complete', { turnId: /./ }, async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined) {
      try {
        track($, following, [{ kind: 'end' }])
      } catch (error) {
        $.ui.log(`to-human: a turn's end could not be followed (${String(error)})`, { to: 'debug' })
      }
    }
    return result
  })

  // A cleared, resumed or forked session's rows are another conversation's,
  // as the view's places are: the runs of the one before are dropped.
  on('classic.SessionStart', { source: /^(?:clear|resume|fork)$/ }, async ($, e, next) => {
    reset($, following, e.session_id)
    return next(e)
  })
}
