import type { EngineInterface, On, SessionAppendInput } from 'claude-code'

import type { FoldRun, Folds, OpenFold, OpenFoldLast } from '../../types/to-human'
import { isMadeUp } from './message'
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
 * The two meet only at a row's place in the transcript (`View.place`).
 */

/** A row as the main conversation keeps it: what `session.append` hands a hook, and the row as stored. */
export type KeptRow = Pick<SessionAppendInput, 'door' | 'origin' | 'uuid' | 'agentId' | 'message'>

/**
 * What one kept row does to the runs, block by block in order: a note, a call
 * or a delivery joins the open run (a call's row known by its call's id, any
 * other by the row's), a result joins its call's run wherever that stands,
 * and a read row closes the open run.
 */
export type Step =
  | { kind: 'note'; id: string; text: string }
  | { kind: 'call'; id: string; tool: string; input: unknown }
  | { kind: 'delivery'; id: string; text: string }
  | { kind: 'result'; call: string }
  | { kind: 'read'; id: string }

const textOf = (content: SessionAppendInput['message']['content']) =>
  content.flatMap((block) => (block.type === 'text' && typeof block.text === 'string' ? [block.text] : [])).join('\n')

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
        block.type === 'tool_result' && typeof block.tool_use_id === 'string' ? [{ kind: 'result', call: block.tool_use_id }] : [],
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

/** A run as the tracker holds it. */
type Run = {
  first: string
  /** The newest row that joined; once the run is closed, its last. */
  last: string
  line?: string
  summary?: string
  isLive: boolean
  /** Its calls whose results have not been kept. */
  running: Set<string>
  /** The tracker saw every row of it: false for a run a module before this one held. */
  isWhole: boolean
}

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

/**
 * A run due its summary: closed, every call's result kept. This milestone
 * makes none, so the run settles at once, its live line let go and its
 * summary, if a module before made one, kept.
 */
function due(run: Run) {
  run.isLive = false
  delete run.line
}

/** Takes the steps of one kept row, in order. */
export function follow(tracker: Tracker, steps: readonly Step[]) {
  for (const step of steps) {
    if (step.kind === 'result') {
      const run = tracker.runOfCall.get(step.call)
      if (run === undefined) continue
      tracker.runOfCall.delete(step.call)
      run.running.delete(step.call)
      if (run !== tracker.open && run.running.size === 0) due(run)
    } else if (step.kind === 'read') {
      const run = tracker.open
      if (run === null) continue
      tracker.open = null
      tracker.closed.push(run)
      if (run.running.size === 0) due(run)
    } else {
      const run = (tracker.open ??= { first: step.id, last: step.id, isLive: true, running: new Set(), isWhole: true })
      run.last = step.id
      run.isLive = true
      if (step.kind === 'call') {
        run.line = lineOf(step.tool, step.input)
        run.running.add(step.id)
        tracker.runOfCall.set(step.id, run)
      }
    }
  }
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

const isFoldRun = (value: unknown): value is FoldRun =>
  typeof value === 'object' && value !== null && typeof (value as { first?: unknown }).first === 'string'

const held = (run: FoldRun, last: unknown = run.last): Run => ({
  first: run.first,
  last: typeof last === 'string' ? last : run.first,
  ...(typeof run.line === 'string' && { line: run.line }),
  ...(typeof run.summary === 'string' && { summary: run.summary }),
  isLive: run.isLive === true,
  running: new Set(),
  isWhole: false,
})

/**
 * Takes up the runs a module before this one published (a reload of the
 * plugin's code loses the module's memory; `$.state` outlives it). The open
 * run goes on, held not whole: its calls' results are unknown here, and so is
 * what it held; its newest row (`openLast`) bounds it when it closes. A closed
 * run still live was waiting on something that died with that module, so it
 * settles with what it had.
 */
export function takeUp(tracker: Tracker, folds: Folds | undefined, open: OpenFold | undefined, openLast: OpenFoldLast | undefined) {
  const runs = folds?.shape === 1 && Array.isArray(folds.runs) ? folds.runs.filter(isFoldRun) : []
  tracker.closed = runs.map((run) => {
    const closed = held(run)
    if (closed.isLive) due(closed)
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
  const from = open === null || open === undefined ? undefined : view.place.get(open.first)
  if (open && from !== undefined && at >= from) return labelFor(open)
  const runs = folds?.runs ?? []
  for (let i = runs.length - 1; i >= 0; i -= 1) {
    const run = runs[i]!
    const [first, last] = [view.place.get(run.first), run.last === undefined ? undefined : view.place.get(run.last)]
    if (first !== undefined && last !== undefined && first <= at && at <= last) return labelFor(run)
  }
  return undefined
}

const FOLDS = { plugin: 'to-human', key: 'folds' } as const
const OPEN = { plugin: 'to-human', key: 'fold' } as const
const OPEN_LAST = { plugin: 'to-human', key: 'foldLast' } as const

/** What one registration of the tracker keeps between its hooks. */
type Following = {
  tracker: Tracker
  /** The rows' steps kept before the start-up read landed, in order; undefined once it has. */
  backlog: Step[][] | undefined
  loading?: Promise<void>
  /** Bumped by a clear, a resume or a fork: a start-up read begun before one takes up nothing. */
  epoch: number
  /** The writes to `$.state`, one after another. */
  writes: Promise<void>
  /** What was last written under each key, as JSON. */
  written: { folds: string; fold: string; foldLast: string }
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

/** Takes up what a module before this one published, once, then the rows that waited for it. */
function load($: EngineInterface, following: Following): Promise<void> {
  following.loading ??= (async () => {
    const at = following.epoch
    try {
      const [folds, open, openLast] = await Promise.all([$.state.get(FOLDS), $.state.get(OPEN), $.state.get(OPEN_LAST)])
      if (at === following.epoch) {
        takeUp(following.tracker, folds.value, open.value, openLast.value)
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
      const waiting = following.backlog ?? []
      following.backlog = undefined
      for (const steps of waiting) follow(following.tracker, steps)
      publish($, following)
    }
  })()
  return following.loading
}

/** Follows one kept row: at once, or after the start-up read while it has not landed. */
function track($: EngineInterface, following: Following, row: KeptRow) {
  const steps = stepsOf(row, following.tracker.spawns)
  if (steps.length === 0) return
  if (following.backlog !== undefined) {
    following.backlog.push(steps)
    void load($, following)
    return
  }
  follow(following.tracker, steps)
  publish($, following)
}

/** Drops the runs of the conversation before, and publishes that. */
function reset($: EngineInterface, following: Following) {
  following.epoch += 1
  following.tracker = newTracker()
  following.backlog = undefined
  following.loading ??= Promise.resolve()
  publish($, following)
}

/**
 * Registers the tracker's hooks. `isOn` is the view's "a mark has been seen";
 * the live lines are published in every session the plugin loads in (a few
 * small writes), so this milestone reads neither it nor `view`, which the
 * summaries' gate and the view's lookup are for.
 *
 * Rows are followed in the order their appends resolve; those kept before
 * the start-up read of `$.state` landed wait for it. Nothing here holds or
 * fails a row's keeping: each hook hands the row on as it was stored.
 */
export function registerFolds(on: On, view: View, isOn: () => boolean) {
  const following: Following = { tracker: newTracker(), backlog: [], epoch: 0, writes: Promise.resolve(), written: { folds: '', fold: '', foldLast: '' } }

  // Each load of the module raises this, the first and every reload.
  on('session.start', { cwd: /./ }, async ($, e, next) => {
    void load($, following)
    return next(e)
  })

  on('session.append', { door: /^[a-z-]+$/ }, async ($, e, next) => {
    const stored = await next(e)
    if (e.agentId === undefined && stored.deny === undefined) {
      try {
        track($, following, { door: e.door, origin: e.origin, uuid: stored.uuid, message: stored.message })
      } catch (error) {
        // The row is kept whatever this hook makes of it; only its run is lost.
        $.ui.log(`to-human: a kept row could not be followed (${String(error)})`, { to: 'debug' })
      }
    }
    return stored
  })

  // A cleared, resumed or forked session's rows are another conversation's,
  // as the view's places are: the runs of the one before are dropped.
  on('classic.SessionStart', { source: /^(?:clear|resume|fork)$/ }, async ($, e, next) => {
    reset($, following)
    return next(e)
  })
}
