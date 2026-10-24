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
function linesOf(value: string | undefined): string[] {
  if (value === undefined || value === '') return []
  return (value.endsWith('\n') ? value.slice(0, -1) : value).split('\n')
}

export const lineCount = (value: string | undefined) => linesOf(value).length

/**
 * A notebook cell's change: a result carries the whole cell before and after,
 * so a replace counts only the lines between those the two bodies share at
 * their start and end; a delete's `new_source` is not drawn, so not counted.
 */
function cellCounts(mode: unknown, before: string | undefined, after: string | undefined): { added: number; removed: number } {
  if (mode === 'insert') return { added: lineCount(after), removed: 0 }
  if (mode === 'delete') return { added: 0, removed: lineCount(before) }
  const old = linesOf(before)
  const now = linesOf(after)
  let head = 0
  while (head < old.length && head < now.length && old[head] === now[head]) head += 1
  let tail = 0
  while (tail < old.length - head && tail < now.length - head && old[old.length - 1 - tail] === now[now.length - 1 - tail]) tail += 1
  return { added: now.length - head - tail, removed: old.length - head - tail }
}

/** A result held for the person's review, not applied: the engine's row says so, and nothing changed to count. */
const isStaged = (output: unknown) => isRecord(output) && output.staged === true

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
 * for any other tool, or for a call that errored, was refused, cut or staged,
 * whose rows stay as the engine draws them (its error, or that it waits for
 * the person's review, is what there is to read).
 * Counts come from the result's patch, which is the change as made; a new
 * file's from what was written.
 */
export function changeOf(props: { tool: string; input: unknown; output?: unknown; isErrored: boolean; isInterrupted: boolean }): FileChange | undefined {
  if (!EDIT_TOOLS.has(props.tool) || props.isErrored || props.isInterrupted || isStaged(props.output)) return undefined
  const input = isRecord(props.input) ? props.input : {}
  const output = isRecord(props.output) ? props.output : undefined
  const path = text(input.file_path) ?? text(input.notebook_path) ?? text(output?.filePath) ?? text(output?.notebook_path)
  if (path === undefined) return undefined
  const isCreate = props.tool === 'Write' && output?.type === 'create'
  if (output === undefined) return { path, isCreate, added: 0, removed: 0, isDone: false }
  if (props.tool === 'NotebookEdit') {
    return { path, isCreate, ...cellCounts(output.edit_mode ?? input.edit_mode, text(output.old_source), text(output.new_source)), isDone: true }
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
const EDITS_ROW = 'to-human-edits-row'
/**
 * An unfolded run's rows stand on the background the fullscreen transcript
 * gives a row a click unfolded. A plugin cannot take a click on the engine's
 * rows themselves (no Box is pressable, and a Button holds only text), so
 * the run folds from its line, which heads the card.
 */
const CARD = 'userMessageBackgroundHover'

/**
 * Folds the rows of file changes into the engine's summary style: a run of
 * edits and writes, with nothing between them, draws as one dim line
 * (`Edited build.py +3, to-human.tsx +40 -12`) where each would draw its
 * call and its whole diff; a press on the line unfolds the run's rows as
 * the engine draws them, on a card under the line, and another folds them
 * back. Registered beneath the
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
  // Results drawn in full before their call's row told what it changed (a window or a
  // resume can draw a result first): the call redraws them once it is summarized.
  const early = new Set<string>()

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
      if ((besideOne || (change !== undefined && early.has(id))) && isOn()) $.ui.invalidate('ui.render')
    }
    if (!isOn() || e.props.isExpanded || change === undefined) return next(e)

    const run = runOf(view.order, changes, id)
    const head = run[0]!
    const { Box, Text, Button } = $.ui.resolve(e)
    if (head !== id) {
      return shown.has(head) ? <Box flexDirection="column" backgroundColor={CARD}>{await next(e)}</Box> : <Box />
    }
    const isShown = shown.has(head)
    const parts = summaryParts(run.flatMap((call) => changes.get(call) ?? []))
    // The pointer brightens the line as it does the engine's own count lines,
    // instead of inverting it as it does any Button.
    const line = (
      <Box key={EDITS_ROW}>
        <Text>{'  '}</Text>
        <Button key={EDITS} plain dimColor hover={{ inverse: false, dimColor: false }} onPress={() => {
          if (!shown.delete(head)) shown.add(head)
        }}>
          {parts.map((part) => (part.bold || part.color ? <Text bold={part.bold} color={part.color}>{part.text}</Text> : part.text))}
          {isShown ? '' : ' ›'}
        </Button>
      </Box>
    )
    return isShown ? (
      <Box flexDirection="column" marginTop={1} backgroundColor={CARD}>
        {line}
        {await next(e)}
      </Box>
    ) : (
      <Box marginTop={1}>{line}</Box>
    )
  })

  // The diff beneath a call is its result's row: drawn only while its run is unfolded.
  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    if (e.surface !== 'terminal' || !isOn() || e.props.isExpanded || e.props.isErrored || isStaged(e.props.output)) return next(e)
    if (!changes.has(e.requestId)) {
      if (EDIT_TOOLS.has(e.props.tool)) early.add(e.requestId)
      return next(e)
    }
    early.delete(e.requestId)
    const run = runOf(view.order, changes, e.requestId)
    const { Box } = $.ui.resolve(e)
    if (!shown.has(run[0]!)) return <Box />
    // The card ends a line below its last diff, as the engine's unfolded rows do.
    return (
      <Box flexDirection="column" backgroundColor={CARD} paddingBottom={run.at(-1) === e.requestId ? 1 : 0}>
        {await next(e)}
      </Box>
    )
  })

  // The line is the terminal's alone.
  on('ui.press', { element: EDITS }, async ($, e, next) => {
    if (e.surface !== 'terminal') return next(e)
    const result = await next(e)
    $.ui.invalidate('ui.render')
    return result
  })
}
