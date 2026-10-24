import type { Color, On } from 'claude-code'

import type { View } from './to-human'

/**
 * The tools that change a file. The engine folds reads, searches and shell
 * commands into one count line (`Read 3 files, ran 2 shell commands`) but
 * draws each of these as its own row with the whole diff beneath it; its own
 * summary of them (`Edited 2 files +34 -53`) is drawn only in a mode this
 * session never runs in.
 */
const EDIT_TOOLS: ReadonlySet<string> = new Set(['Edit', 'Write', 'NotebookEdit'])

/** What one call did to one file, as its summary line counts it. */
export type FileChange = {
  path: string
  /** A `Write` that made the file. */
  isCreate: boolean
  added: number
  removed: number
  /** False while the call has no result yet (running, or waiting at the permission dialog). */
  isDone: boolean
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null
const text = (value: unknown) => (typeof value === 'string' ? value : undefined)

/** The lines a text holds, a final newline ending its last line rather than opening one. */
export function lineCount(value: string | undefined): number {
  if (value === undefined || value === '') return 0
  return value.split('\n').length - (value.endsWith('\n') ? 1 : 0)
}

/** The lines a `structuredPatch` adds and removes; undefined where there is none to read. */
function patchCounts(patch: unknown): { added: number; removed: number } | undefined {
  if (!Array.isArray(patch)) return undefined
  let added = 0
  let removed = 0
  for (const hunk of patch) {
    if (!isRecord(hunk) || !Array.isArray(hunk.lines)) continue
    for (const line of hunk.lines) {
      if (typeof line !== 'string') continue
      if (line.startsWith('+')) added += 1
      else if (line.startsWith('-')) removed += 1
    }
  }
  return { added, removed }
}

/**
 * What a call of a file-changing tool did, read from its row's props; none
 * for any other tool, or for a call that errored, was refused or cut, whose
 * row stays as the engine draws it (its error is what there is to read).
 * Counts come from the result's patch, which is the change as made; a new
 * file's from what was written.
 */
export function changeOf(props: { tool: string; input: unknown; output?: unknown; isErrored: boolean; isInterrupted: boolean }): FileChange | undefined {
  if (!EDIT_TOOLS.has(props.tool) || props.isErrored || props.isInterrupted) return undefined
  const input = isRecord(props.input) ? props.input : {}
  const output = isRecord(props.output) ? props.output : undefined
  const path = text(input.file_path) ?? text(input.notebook_path) ?? text(output?.filePath) ?? text(output?.notebook_path)
  if (path === undefined) return undefined
  const isCreate = props.tool === 'Write' && output?.type === 'create'
  if (output === undefined) return { path, isCreate, added: 0, removed: 0, isDone: false }
  if (props.tool === 'NotebookEdit') {
    return { path, isCreate, added: lineCount(text(output.new_source)), removed: lineCount(text(output.old_source)), isDone: true }
  }
  const counts = patchCounts(output.structuredPatch)
  if (isCreate && (counts === undefined || counts.added === 0)) {
    return { path, isCreate, added: lineCount(text(output.content) ?? text(input.content)), removed: 0, isDone: true }
  }
  return { path, isCreate, ...(counts ?? { added: 0, removed: 0 }), isDone: true }
}

/** One piece of a summary line: its text, and how the group line draws it. */
export type Part = { text: string; bold?: true; color?: Color }

/** Past this many files a clause counts them, as the engine's own line does, instead of naming each. */
const NAMED_MAX = 3

const stat = (added: number, removed: number): Part[] => [
  ...(added > 0 ? [{ text: ' ' }, { text: `+${added}`, color: 'diffAddedWord' as const }] : []),
  ...(removed > 0 ? [{ text: ' ' }, { text: `-${removed}`, color: 'diffRemovedWord' as const }] : []),
]

/**
 * A run of file changes as one line in the engine's group style: a clause
 * for the files it edited and one for those it created, each file by its
 * name with its own `+added -removed`, as Claude Desktop names them (two
 * files of one name by their folder too), and past `NAMED_MAX` files a
 * count. A file changed by several calls is one entry; one still running is
 * named with `…` and the clause's verb is in progress (`Editing`).
 */
export function summaryParts(changes: readonly FileChange[]): Part[] {
  const byPath = new Map<string, FileChange>()
  for (const change of changes) {
    const known = byPath.get(change.path)
    byPath.set(
      change.path,
      known === undefined
        ? { ...change }
        : { ...known, added: known.added + change.added, removed: known.removed + change.removed, isDone: known.isDone && change.isDone },
    )
  }
  const files = [...byPath.values()]
  const base = (path: string) => path.split('/').filter(Boolean).at(-1) ?? path
  const clash = new Set(files.map((file) => base(file.path)).filter((name, i, names) => names.indexOf(name) !== i))
  const nameOf = (path: string) => (clash.has(base(path)) ? path.split('/').filter(Boolean).slice(-2).join('/') : base(path))

  const parts: Part[] = []
  const clause = (verb: [done: string, live: string], group: FileChange[]) => {
    if (group.length === 0) return
    const isLive = group.some((file) => !file.isDone)
    const word = verb[isLive ? 1 : 0]
    parts.push({ text: `${parts.length === 0 ? word[0]!.toUpperCase() + word.slice(1) : `, ${word}`} ` })
    if (group.length > NAMED_MAX) {
      const done = group.filter((file) => file.isDone)
      const sum = (key: 'added' | 'removed') => done.reduce((total, file) => total + file[key], 0)
      parts.push({ text: String(group.length), bold: true }, { text: ' files' }, ...stat(sum('added'), sum('removed')), ...(isLive ? [{ text: '…' }] : []))
      return
    }
    group.forEach((file, i) => {
      if (i > 0) parts.push({ text: ', ' })
      parts.push({ text: nameOf(file.path), bold: true }, ...(file.isDone ? stat(file.added, file.removed) : [{ text: '…' }]))
    })
  }
  clause(['edited', 'editing'], files.filter((file) => !file.isCreate))
  clause(['created', 'creating'], files.filter((file) => file.isCreate))
  return parts
}

/**
 * The calls of the run of file changes `id` stands in, in order: the rows
 * beside it in the transcript that are file changes too. The first draws the
 * run's line; the rest draw nothing.
 */
export function runOf(order: readonly string[], changes: ReadonlyMap<string, FileChange>, id: string): string[] {
  let at = order.indexOf(id)
  if (at < 0) return [id]
  while (at > 0 && changes.has(order[at - 1]!)) at -= 1
  const run: string[] = []
  for (; at < order.length && changes.has(order[at]!); at += 1) run.push(order[at]!)
  return run.length === 0 ? [id] : run
}

const EDITS = 'to-human-edits'

/**
 * Folds the rows of file changes into the engine's summary style: a run of
 * edits and writes, with nothing between them, draws as one dim line
 * (`Edited build.py +3, to-human.tsx +40 -12`) where each would draw its
 * call and its whole diff; a press on the line unfolds the run's rows as
 * the engine draws them, and another folds them back. Registered beneath the
 * view's hooks, so it draws wherever the view shows a row as the engine
 * would: an unfolded run of working record, the full transcript. The ctrl+o
 * transcript and `--verbose` keep every diff, other surfaces draw their own
 * rows, and nothing changes until the view is on (`isOn`).
 */
export function registerEdits(on: On, view: View, isOn: () => boolean) {
  const changes = new Map<string, FileChange>()
  // What each call's line last read of it, so a change that moves its run's line (a call
  // joining it, a result arriving, an error taking a call out) asks the run's rows again.
  const seen = new Map<string, string>()
  // The runs unfolded by a press, by their first call.
  const shown = new Set<string>()

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (e.surface !== 'terminal' || !EDIT_TOOLS.has(e.props.tool)) return next(e)
    const id = e.requestId
    const change = changeOf(e.props)
    const signature = change === undefined ? '' : JSON.stringify(change)
    if (seen.get(id) !== signature) {
      seen.set(id, signature)
      if (change === undefined) changes.delete(id)
      else changes.set(id, change)
      const at = view.order.indexOf(id)
      const besideOne = at >= 0 && [view.order[at - 1], view.order[at + 1]].some((other) => other !== undefined && changes.has(other))
      if (besideOne && isOn()) $.ui.invalidate('ui.render')
    }
    if (!isOn() || e.props.isExpanded || change === undefined) return next(e)

    const run = runOf(view.order, changes, id)
    const head = run[0]!
    if (head !== id) {
      const { Box } = $.ui.resolve(e)
      return shown.has(head) ? next(e) : <Box />
    }
    const { Box, Text, Button } = $.ui.resolve(e)
    const isShown = shown.has(head)
    const parts = summaryParts(run.flatMap((call) => changes.get(call) ?? []))
    const line = (
      <Box marginTop={1}>
        <Text>{'  '}</Text>
        <Button key={EDITS} plain dimColor onPress={() => {
          if (!shown.delete(head)) shown.add(head)
        }}>
          {parts.map((part) => (part.bold || part.color ? <Text bold={part.bold} color={part.color}>{part.text}</Text> : part.text))}
          {isShown ? '' : ' ›'}
        </Button>
      </Box>
    )
    return isShown ? (
      <Box flexDirection="column">
        {line}
        {await next(e)}
      </Box>
    ) : (
      line
    )
  })

  // The diff beneath a call is its result's row: drawn only while its run is unfolded.
  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    if (e.surface !== 'terminal' || !isOn() || e.props.isExpanded || e.props.isErrored || !changes.has(e.requestId)) return next(e)
    if (shown.has(runOf(view.order, changes, e.requestId)[0]!)) return next(e)
    const { Box } = $.ui.resolve(e)
    return <Box />
  })

  // The line is the terminal's alone.
  on('ui.press', { element: EDITS }, async ($, e, next) => {
    if (e.surface !== 'terminal') return next(e)
    const result = await next(e)
    $.ui.invalidate('ui.render')
    return result
  })
}
