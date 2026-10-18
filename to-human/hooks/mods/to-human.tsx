import type { EngineInterface, On, PromptOrigin, RenderElement, RenderInput } from 'claude-code'

/** The doperpowers ask mod's tool, the model's one way to ask the human in an interactive session. */
const ASK_TOOL = 'mcp__doperpowers__AskUserQuestion'

/**
 * The mark the `to-human` output style asks the model to write: a message
 * to the human. The old `to-human`, `essential`, `need-input` and `insight`
 * marks read as messages too (a `need-input` question's `<choice>` lines
 * stay in its text). Everything outside a mark is the model's working
 * record.
 */
export type Kind = 'message'

export type Span = {
  kind: Kind
  text: string
  /** True while the closing tag has not arrived: the span is still streaming. */
  isOpen: boolean
}

export type Parsed = {
  spans: Span[]
  /** True when non-blank text sits outside every span. */
  hasRecord: boolean
}

// Code regions (grammar 2): half-open [start, end) offsets into the text, in order.
type CodeRegion = readonly [start: number, end: number]

// A fence line's two patterns: group 1 the fence run, group 2 what follows it on the line (an opening fence's info string
// a closing fence's trailing mark tags, empty in the strict reading).
type Fences = { open: RegExp; close: RegExp }
const STRICT: Fences = { open: /^[ \t]*(`{3,}|~{3,})(.*)$/, close: /^[ \t]*(`{3,}|~{3,})[ \t]*()$/ }
// MAWS's glued recovery reading: mark tags are transparent at a fence line's edges, so `<to-human>` glued
// before an opening fence or `</to-human>` after a closing one still means the fence, the tags outside the region. It
// is a recovery only: a report the strict reading balances never reads through it.
const MARK_TAGS = String.raw`(?:<\/?(?:message|to-human|essential|need-input|insight)>[ \t]*)*`
const GLUED: Fences = {
  open: new RegExp(String.raw`^[ \t]*${MARK_TAGS}(\x60{3,}|~{3,})(.*)$`),
  close: new RegExp(String.raw`^[ \t]*(\x60{3,}|~{3,})[ \t]*(${MARK_TAGS})$`),
}

function codeRegions(text: string): CodeRegion[] {
  return regionsOf(text, STRICT)
}

function regionsOf(text: string, fences: Fences): CodeRegion[] {
  const regions: CodeRegion[] = []
  let paragraph: [number, number] | null = null
  let fence: { char: string; length: number; start: number } | null = null
  const closeParagraph = () => {
    if (paragraph !== null) inlineSpans(text, paragraph[0], paragraph[1], regions)
    paragraph = null
  }
  for (let at = 0; at <= text.length;) {
    const newline = text.indexOf('\n', at)
    const end = newline === -1 ? text.length : newline
    const line = text.slice(at, end)
    if (fence !== null) {
      const close = fences.close.exec(line)
      if (close !== null && close[1]![0]! === fence.char && close[1]!.length >= fence.length) {
        regions.push([fence.start, end - close[2]!.length])
        fence = null
      }
    } else {
      const open = fences.open.exec(line)
      // A backtick fence's info string holds no backtick; such a line is an inline span instead.
      if (open !== null && !(open[1]![0]! === '`' && open[2]!.includes('`'))) {
        closeParagraph()
        fence = { char: open[1]![0]!, length: open[1]!.length, start: end - open[1]!.length - open[2]!.length }
      } else if (line.trim() === '') closeParagraph()
      else paragraph = paragraph === null ? [at, end] : [paragraph[0], end]
    }
    at = end + 1
  }
  if (fence !== null) regions.push([fence.start, text.length])
  closeParagraph()
  return regions.sort((a, b) => a[0] - b[0])
}

// A run of N backticks opens a span closed by the next run of exactly N; a run with no partner is literal backticks.
// Linear in the runs: one pass links each run to the next run of its length, then the walk pairs left to right.
function inlineSpans(text: string, start: number, end: number, regions: CodeRegion[]) {
  const runs = [...text.slice(start, end).matchAll(/`+/g)]
  const next: number[] = runs.map(() => -1)
  const latest = new Map<number, number>()
  runs.forEach((run, i) => {
    const previous = latest.get(run[0].length)
    if (previous !== undefined) next[previous] = i
    latest.set(run[0].length, i)
  })
  for (let i = 0; i < runs.length; i++) {
    const close = next[i]!
    if (close === -1) continue
    regions.push([start + runs[i]!.index, start + runs[close]!.index + runs[close]![0].length])
    i = close
  }
}

// Whether an offset lies in one of `codeRegions`' regions (binary search over the ordered, disjoint regions).
const insideCode = (regions: readonly CodeRegion[]) => (offset: number): boolean => {
  let low = 0
  let high = regions.length - 1
  while (low <= high) {
    const middle = (low + high) >> 1
    if (offset < regions[middle]![0]) high = middle - 1
    else if (offset >= regions[middle]![1]) low = middle + 1
    else return true
  }
  return false
}

// The code-region reading is shared with MAWS grammar 2. Unlike stored text,
// this display parser still draws unclosed marks as open.
const TAG = /<(\/?)(message|to-human|essential|need-input|insight)>/g

function readingOf(text: string, regions: readonly CodeRegion[]) {
  const inCode = insideCode(regions)
  const tokens = [...text.matchAll(TAG)].filter((token) => !inCode(token.index))
  const stack: string[] = []
  let balanced = true
  for (const token of tokens) {
    if (!token[1]) stack.push(token[2]!)
    else if (stack.at(-1) === token[2]) stack.pop()
    else { balanced = false; stack.length = 0 }
  }
  return { inCode, tokens, balanced: balanced && stack.length === 0 }
}

/**
 * Splits text still carrying its marks. Marks may nest (an old `<insight>`
 * inside a `<message>`): each contiguous run of text under one mark is a
 * span of its own, in the order written. An unclosed mark runs to the end.
 */
function parseMarked(text: string): Parsed {
  let reading = readingOf(text, codeRegions(text))
  if (!reading.balanced) {
    const glued = readingOf(text, regionsOf(text, GLUED))
    if (glued.balanced) reading = glued
  }
  const { tokens } = reading
  const spans: Span[] = []
  // One entry per open mark, innermost last; `span` is the entry's current
  // run of text, or null once an inner mark has interrupted it.
  const open: { tag: string; kind: Kind; span: Span | null }[] = []
  let outside = ''
  let last = 0

  const take = (piece: string) => {
    const top = open[open.length - 1]
    if (!top) {
      outside += piece
    } else if (top.span) {
      top.span.text += piece
    } else if (piece.trim() !== '') {
      top.span = { kind: top.kind, text: piece, isOpen: true }
      spans.push(top.span)
    }
  }

  const close = (entry: { span: Span | null }) => {
    if (entry.span) {
      entry.span.isOpen = false
    }
    entry.span = null
  }

  for (const match of tokens) {
    const [whole, slash] = match
    const tag = match[2] as string
    const kind: Kind = 'message'
    const at = match.index ?? 0
    take(text.slice(last, at))
    last = at + whole.length

    if (slash === '') {
      const top = open[open.length - 1]
      if (top) {
        close(top)
      }
      const span: Span = { kind, text: '', isOpen: true }
      spans.push(span)
      open.push({ tag, kind, span })
    } else {
      const depth = open.map((entry) => entry.tag).lastIndexOf(tag)
      if (depth === -1) {
        continue // a stray closing tag: nothing to close
      }
      while (open.length > depth) {
        close(open.pop()!)
      }
    }
  }

  take(text.slice(last))

  for (const span of spans) {
    span.text = span.text.trim()
  }

  return {
    spans: spans.filter((span) => span.text !== '' || span.isOpen),
    hasRecord: outside.trim() !== '',
  }
}

/**
 * What `to-human-stream.sh` leaves behind. That hook draws the marks while
 * the message streams, so by the time the message is whole its text carries
 * the hook's headers and dimmed record instead of the tags: a header is the
 * mark's label in its own bold color, a dimmed run is working record. The
 * old labels (`to human`, `essential`, `need input`, `insight`) read as
 * messages.
 *
 * The first group is the header's color, the second a dimmed run's text.
 */
const RENDERED = /\[1;(3[2356]|38;2;215;119;87)m(?:message|to human|essential|need input|insight)\[0m|\[2m([\s\S]*?)\[0m/g

const HEADER = /\[1;(?:3[2356]|38;2;215;119;87)m(?:message|to human|essential|need input|insight)\[0m/

const SGR = /\u001b\[[0-9;]*m/g

const KIND_OF_COLOR: Record<string, Kind> = {
  '38;2;215;119;87': 'message',
  '36': 'message',
  '32': 'message',
  '35': 'message',
  '33': 'message',
}

/**
 * Splits text the streaming hook already drew. A header opens a span that
 * runs to the next header; a dimmed run is record and ends the span it
 * follows, which is how a mark's close survives a form that has no closing
 * marker.
 */
function parseRendered(text: string): Parsed | null {
  // Color escapes are not Markdown syntax. Scan the visible text, then track
  // visible offsets through the raw tokens so dimmed fences still fence code.
  const inCode = insideCode(codeRegions(text.replace(SGR, '')))
  const spans: Span[] = []
  let outside = ''
  let current: Span | null = null
  let last = 0
  let visibleAt = 0
  let hasHeader = false

  const take = (piece: string) => {
    if (piece === '') {
      return
    }
    if (current) {
      current.text += piece
    } else {
      outside += piece
    }
  }

  for (const match of text.matchAll(RENDERED)) {
    const [whole, color, dimmed] = match
    const at = match.index ?? 0
    const before = text.slice(last, at)
    take(before)
    visibleAt += before.replace(SGR, '').length
    last = at + whole.length

    if (color !== undefined && inCode(visibleAt)) {
      take(whole)
    } else if (color !== undefined) {
      hasHeader = true
      current = { kind: KIND_OF_COLOR[color] as Kind, text: '', isOpen: false }
      spans.push(current)
    } else {
      current = null
      outside += dimmed ?? ''
    }
    visibleAt += whole.replace(SGR, '').length
  }

  take(text.slice(last))

  for (const span of spans) {
    span.text = span.text.trim()
  }

  return hasHeader ? { spans: spans.filter((span) => span.text !== ''), hasRecord: outside.trim() !== '' } : null
}

/**
 * Splits one assistant text block into its marked spans and notes whether a
 * working record surrounds them, in whichever of the two forms the block
 * reaches the transcript in: its own marks, or the headers the streaming
 * hook drew over them.
 */
export function parse(text: string): Parsed {
  // A real rendered header identifies hook output, whose remaining raw tags
  // are quoted examples. A header quoted in code does not select this reader.
  return (HEADER.test(text) ? parseRendered(text) : null) ?? parseMarked(text)
}

/**
 * What one row of the transcript is: the person's prompt; a row they read
 * (an assistant message carrying marks, a question they answered, an
 * agent's dispatch, an agent's failure, an API error that ended the turn); a mixed row, a message
 * carrying marks with unmarked text beside them, which the person reads and
 * which opens the run of working record after it; or working record (an
 * unmarked message, a tool call and its result, agent messages and
 * background notifications).
 */
export type RowKind = 'user' | 'marked' | 'mixed' | 'record'

/**
 * The origins of a prompt row that is a delivery to the session and not the
 * person's own words: a task's notification, a schedule firing, another
 * session's or a coordinator's message, an observer's report, a plugin's
 * submission. These deliveries are working record. An unknown origin without
 * a sender or task is taken as the person's:
 * hiding their own prompt is the worse mistake.
 */
const DELIVERED: ReadonlySet<string> = new Set([
  'task-notification',
  'scheduled-trigger',
  'peer',
  'peer-send-message',
  'projects-relay',
  'coordinator',
  'observer',
  'observer-activity',
  'plugin',
])

/** The origins the person's own gesture stamps: Enter at the prompt, and a Remote Control client's message. */
const TYPED: ReadonlySet<string> = new Set(['composer', 'bridge'])

/**
 * The line sminos opens every delivery with, whichever way it reaches the
 * session (the bridge's prompt, a background job's reply, the inbox), naming
 * who sent it: `human` for the person, else another session's alias. A
 * `send` opens `[sminos message from <sender> id=<id>]`; anything else (a
 * `say`) opens `[sminos chat <project> <ref> from <sender> → @you|@all]`,
 * with ` | unread N` before the bracket when messages are waiting. The
 * project's name is free text in its `.smns` (spaces allowed), so the chat
 * frame is read from its tail, where the sender sits, not from its head.
 */
const SMINOS_FRAMES = [
  /^\[sminos message from (\S+) id=[0-9a-f]{8}\]/,
  /^\[sminos chat [^\n]* from (\S+) → @(?:you|all)(?: \| unread \d+)?\]/,
]

/** Who a sminos delivery's opening line names as its sender, if it opens with one. */
function deliverySender(text: string): string | undefined {
  for (const frame of SMINOS_FRAMES) {
    const sender = frame.exec(text)?.[1]
    if (sender !== undefined) {
      return sender
    }
  }
  return undefined
}

/**
 * How the doperpowers ask mod opens the plugin prompt that hands the model
 * the person's answer to an async question (its `deliveryText`), possibly
 * after the framing the engine stores before a plugin prompt. It stays the
 * person's: the ask's own row does not draw the feedback a person gives with
 * "Chat about this" or the notes added to an answer, so this row carries
 * their words whole.
 */
const ASK_DELIVERY = /^(?:The doperpowers plugin sent a message:\s*)?The human responded to your async AskUserQuestion \(call /

/** The props of a prompt row that say what it is. */
export type PromptRowProps = {
  origin?: Pick<PromptOrigin, 'kind'>
  /** What the row shows; a delivery's text opens with its sender's frame. */
  text?: string
  /** Present when someone other than the person sent it: an agent, a teammate, another session, a channel. */
  from?: { name: string }
  /** Present on a notification row: the background task it reports on, an agent's run among them. */
  task?: { id?: string; toolUseId?: string; status?: string }
}

/**
 * The person's own words stay visible. Messages delivered by agents and
 * background notifications belong to the working record, except the
 * failure of an agent the report shows the spawn of (`spawns`, the calls'
 * ids): the spawn stays in the report, so its failure does too. A sminos
 * delivery is read by its frame: the person's, sent from elsewhere, stays,
 * and another session's is working record, though the bridge submits both as
 * the person's words. The ask mod's delivery of an async answer stays too.
 */
export function promptRow(props: PromptRowProps, spawns: ReadonlySet<string> = new Set()): RowKind {
  const { task } = props
  if (task?.status === 'failed' && task.toolUseId !== undefined && spawns.has(task.toolUseId)) {
    return 'marked'
  }
  if (props.from !== undefined || task !== undefined) {
    return 'record'
  }
  const kind = props.origin?.kind
  if (ASK_DELIVERY.test(props.text ?? '')) {
    return 'user'
  }
  const sender = kind !== undefined && TYPED.has(kind) ? undefined : deliverySender(props.text ?? '')
  if (sender !== undefined) {
    return sender === 'human' ? 'user' : 'record'
  }
  return kind !== undefined && DELIVERED.has(kind) ? 'record' : 'user'
}

/**
 * The first row of the run of working record `id` belongs to: walking back
 * over the rows that are working record too and stopping at a prompt or at
 * a message that carries marks. A mixed message, marks with unmarked text
 * beside them, is where the run after it starts: its own record and the run
 * open and close as one, under its one button, so two things the person
 * reads have one `[ working record ]` between them and not two. A run of
 * unmarked messages draws as one button rather than one button each, so the
 * report reads as a report; this names the row that draws it, and the rest
 * of the run draw nothing.
 */
export function runStart(
  order: readonly string[],
  rowOf: ReadonlyMap<string, RowKind>,
  id: string,
): string {
  let at = order.indexOf(id)
  if (at < 0 || rowOf.get(id) === 'mixed') {
    return id
  }
  while (at > 0 && rowOf.get(order[at - 1] as string) === 'record') {
    at -= 1
  }
  if (at > 0 && rowOf.get(order[at - 1] as string) === 'mixed') {
    at -= 1
  }
  return order[at] as string
}

/** Whether a row stands in a run of working record: as record, or as the mixed message that opens one. */
const inRun = (kind: RowKind | undefined) => kind === 'record' || kind === 'mixed'

/**
 * The last message of the run of working record `id` belongs to: walking
 * forward over the rows that are working record too. This is the row that
 * draws the run's `[ fold to report ]`, under itself, where the person is
 * when they finish reading; as the run grows, the button moves down with it.
 */
export function runEnd(
  order: readonly string[],
  rowOf: ReadonlyMap<string, RowKind>,
  id: string,
): string {
  let at = order.indexOf(id)
  if (at < 0) {
    return id
  }
  while (at < order.length - 1 && rowOf.get(order[at + 1] as string) === 'record') {
    at += 1
  }
  return order[at] as string
}

/**
 * A span's body is drawn as its own `Markdown`, on every surface. A render
 * answer to a remote surface carries one props, so of several blocks handed
 * back beneath the hook only the first can draw there: Claude Desktop
 * portals its native row into the first `engine` node and draws nothing at
 * the rest, which left every span after the first label-only (2026-10-03).
 * The terminal drew the engine's block until 2026-10-14, but that block
 * carries the engine's row margin, a blank line between the label and the
 * body. `Markdown.text` took at most 10000 characters and takes no control
 * character but tab and newline.
 */
const MARKDOWN_MAX = 10000

/**
 * A span's text as `Markdown` accepts it: residual escape sequences and
 * control characters out, and cut into blocks under the cap at paragraph
 * breaks (a paragraph over the cap is cut where it must be).
 */
export function markdownBlocks(text: string): string[] {
  const clean = text.replace(/\u001b\[[0-9;]*m/g, '').replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '')
  const blocks: string[] = []
  let current = ''
  const push = (block: string) => {
    if (block !== '') {
      blocks.push(block)
    }
  }
  for (const paragraph of clean.split(/\n{2,}/)) {
    const joined = current === '' ? paragraph : `${current}\n\n${paragraph}`
    if (Array.from(joined).length <= MARKDOWN_MAX) {
      current = joined
      continue
    }
    push(current)
    let rest = Array.from(paragraph)
    while (rest.length > MARKDOWN_MAX) {
      push(rest.slice(0, MARKDOWN_MAX).join(''))
      rest = rest.slice(MARKDOWN_MAX)
    }
    current = rest.join('')
  }
  push(current)
  return blocks
}

/**
 * A link to a local file, as the human's CLAUDE.md asks it written:
 * `[name](/absolute/path)`, a line as GitHub writes one on the end of the
 * target (`#L42`, `#L42-L60`). On the terminal the view draws it as an
 * explicit `file:` link behind a file icon and answers a plain click on it
 * (`ui.press` below), opening VS Code at the line; a cmd click stays the
 * terminal's, which hands the `file:` URL to the file's default app. A link
 * with any part in code, an escaped opener, or an href the engine would refuse
 * (`pressableLinks` entries past 2048 characters refuse the whole row) stays
 * as written. The target takes one level of parentheses (`app/(auth)/page.tsx`).
 */
const FILE_LINK = /(?<!\\)\[([^[\]\n]*)\]\(((?:\/|file:\/\/\/)(?:[^()\s]|\([^()\s]*\))*)\)/g
const HREF_MAX = 2048
/** nf-cod-file, VS Code's own file glyph, from the terminal's Nerd Font. */
const FILE_ICON = ''
const LINKS = 'to-human-links:'

/** A block with its file links drawn as the view answers them, and their targets as drawn. */
export function fileLinks(block: string): { text: string; targets: string[] } {
  const inCode = insideCode(codeRegions(block))
  const targets: string[] = []
  const text = block.replace(FILE_LINK, (link, name: string, target: string, offset: number) => {
    if (inCode(offset) || inCode(offset + link.length - 1)) return link
    const href = target.startsWith('/') ? `file://${target.replace(/[^\x21-\x7e]/gu, encodeURIComponent)}` : target
    if (href.length > HREF_MAX) return link
    targets.push(href)
    return `[${FILE_ICON} ${name}](${href})`
  })
  return { text, targets }
}

/** What opens a pressed file link in VS Code: the file, at the line its target names. */
export function editorUrl(href: string): string | undefined {
  const match = /^(?:file:\/\/)?(\/[^?#]*)[^#]*(?:#L(\d+))?/.exec(href)
  if (match === null) return undefined
  return `vscode://file${match[1]}${match[2] === undefined ? '' : `:${match[2]}`}`
}

const STYLE: Record<Kind, { label: string; color: string }> = {
  message: { label: 'message', color: 'claude' },
}

const TOGGLE = 'to-human-toggle'
const MODE = 'to-human-mode'

const isSpawn = (tool: string) => tool === 'Agent' || tool === 'Workflow'

/** Questions (the built-in's and the ask mod's) and agent spawns stay in the report; messaging is working record. */
export const isRead = (tool: string) => tool === 'AskUserQuestion' || tool === ASK_TOOL || isSpawn(tool)

/**
 * What the view keeps between draws: the rows unfolded by a button (a marked
 * message by its own, a run of working record by the one button that stands
 * for it, keyed by the row the run starts at), and the rows drawn so far, in
 * the transcript's order, with what each one is.
 *
 * The order rows first draw in is not the transcript's: the fullscreen
 * transcript lays out only the rows near its window, a resumed session's
 * newest first, and a row that arrived while the human was scrolled away
 * draws once they scroll to it. So each row's place is read from the
 * transcript file when a session is resumed and taken from each append after;
 * a row that draws before its place is known stands after every row appended
 * by then.
 */
export type View = {
  unfolded: Set<string>
  order: string[]
  rowOf: Map<string, RowKind>
  /** Each row's place in the transcript, by its id (a tool row's is its call's `tool_use_id`). */
  place: Map<string, number>
  /** The place a row took when it drew before its own was known. */
  guess: Map<string, number>
  /** The rows appended since the module loaded, each placed past the file's. */
  appended: number
  /** Whether the view folds now: a mark has been seen and the whole transcript is not asked for. */
  isFolding: () => boolean
}

export const newView = (isFolding: () => boolean): View => ({
  unfolded: new Set(),
  order: [],
  rowOf: new Map(),
  place: new Map(),
  guess: new Map(),
  appended: 0,
  isFolding,
})

/** A group of calls is known by its first call's id, which is where it stands. */
const GROUP = 'group:'
/** Where the rows appended while the session runs are placed: past any line of a file. */
const LIVE = 1e12

const keyOf = (id: string) => (id.startsWith(GROUP) ? id.slice(GROUP.length) : id)

function placeOf(view: View, id: string): number {
  const key = keyOf(id)
  return view.place.get(key) ?? view.guess.get(key) ?? Infinity
}

/** The index `id` takes in `order`: after every drawn row placed at or before it. */
function slotOf(view: View, id: string): number {
  const at = placeOf(view, id)
  let low = 0
  let high = view.order.length
  while (low < high) {
    const middle = (low + high) >> 1
    if (placeOf(view, view.order[middle] as string) <= at) {
      low = middle + 1
    } else {
      high = middle
    }
  }
  return low
}

/** Sorts the drawn rows by their places, now that more are known; whether any moved. */
export function reorder(view: View): boolean {
  const sorted = view.order
    .map((id, i) => ({ id, i, at: placeOf(view, id) }))
    .sort((a, b) => (a.at === b.at ? a.i - b.i : a.at < b.at ? -1 : 1))
    .map(({ id }) => id)
  if (sorted.every((id, i) => id === view.order[i])) {
    return false
  }
  view.order.splice(0, view.order.length, ...sorted)
  return true
}

/** Places `ids` in the order given, from `at` by `step`, each one whose place is not known yet. */
export function placeAll(view: View, ids: readonly string[], at = 0, step = 1) {
  ids.forEach((id, i) => {
    if (!view.place.has(id)) {
      view.place.set(id, at + i * step)
    }
  })
}

/**
 * The search that lists a transcript's rows in its order: each row's id, and
 * a tool call's id where its call is written.
 */
export function placeArgs(path: string): string[] {
  return ['grep', '-o', '-E', '"uuid":"[^"]+"|"type":"tool_use","id":"[^"]+"', path]
}

/** The ids `placeArgs`' output names, in the transcript's order. */
export function placesIn(stdout: string): string[] {
  return stdout.split('\n').flatMap((line) => {
    const id = /"(?:uuid|id)":"([^"]+)"$/.exec(line)?.[1]
    return id === undefined ? [] : [id]
  })
}

/** What a drawn row reads of its run: whether it opens it, whether the run is unfolded, and then whether it ends it. */
function shapeOf(view: View, id: string | undefined): string {
  if (id === undefined || !inRun(view.rowOf.get(id))) {
    return ''
  }
  const start = runStart(view.order, view.rowOf, id)
  const isOpen = view.unfolded.has(start)
  return `${start === id}:${isOpen}:${isOpen && runEnd(view.order, view.rowOf, id) === id}`
}

/**
 * Notes a row as it draws: its place among the rows drawn so far, and what it
 * is. A row that lands beside another, or turns into a kind that ends or joins
 * its run, can change what that neighbour draws (whether it opens its run and
 * draws `[ working record ]`, whether it ends an unfolded one and draws
 * `[ fold to report ]`), and the neighbour's drawing is cached as it was: the
 * rows are asked for again. So is a turn's closing line, which reads the row
 * before it, when a row lands among those already drawn while a run is open.
 */
function see($: EngineInterface, view: View, requestId: string, kind: RowKind) {
  const { order, rowOf } = view
  const known = rowOf.get(requestId)
  if (known === kind) {
    return
  }
  const key = keyOf(requestId)
  if (known === undefined && !view.place.has(key) && !view.guess.has(key)) {
    view.guess.set(key, LIVE + view.appended + 0.5)
  }
  const at = known === undefined ? slotOf(view, requestId) : order.indexOf(requestId)
  const neighbours = [order[at - 1], order[known === undefined ? at : at + 1]]
  const shapes = neighbours.map((id) => shapeOf(view, id))
  if (known === undefined) {
    order.splice(at, 0, requestId)
  }
  rowOf.set(requestId, kind)
  const isAmong = known === undefined && at < order.length - 1 && view.unfolded.size > 0
  if (view.isFolding() && (isAmong || neighbours.some((id, i) => shapeOf(view, id) !== shapes[i]))) {
    $.ui.invalidate('ui.render')
  }
}

function toggle(unfolded: Set<string>, id: string) {
  if (unfolded.has(id)) {
    unfolded.delete(id)
  } else {
    unfolded.add(id)
  }
}

/**
 * A row of working record, drawn as its run is. Folded, the row the run
 * starts at draws the one `[ working record ]` button and the rest draw
 * nothing. Unfolded, each row is the engine's own drawing, as the transcript
 * draws it, and the row the run ends at draws `[ fold to report ]` under it,
 * where the person is when they finish reading.
 *
 * `id` names the row when it is not the request's (a group is known by its
 * first call's). A call's row and its result's share an id: `opens` is false
 * for the one that never carries the run's button (the result's, whose call
 * drew it), `closes` for the one that is not the last of its row (the
 * call's, once its result is there to draw beneath it).
 */
async function recordRow<E extends RenderInput>(
  $: EngineInterface,
  e: E,
  next: (e: E) => Promise<RenderElement>,
  view: View,
  {
    bullet = '  ',
    id = e.requestId,
    opens = true,
    closes = true,
  }: { bullet?: string; id?: string; opens?: boolean; closes?: boolean } = {},
): Promise<RenderElement> {
  const { Box, Text, Button } = $.ui.resolve(e)
  const start = runStart(view.order, view.rowOf, id)
  const toggleRun = () => toggle(view.unfolded, start)

  if (!view.unfolded.has(start)) {
    return opens && start === id ? (
      <Box marginTop={1}>
        <Text dimColor>{bullet}</Text>
        <Button key={TOGGLE} label="working record" dimColor onPress={toggleRun} />
      </Box>
    ) : (
      <Box />
    )
  }

  const isEnd = closes && runEnd(view.order, view.rowOf, id) === id
  return (
    <Box flexDirection="column">
      {await next(e)}
      {isEnd ? (
        <Box paddingLeft={2}>
          <Button key={TOGGLE} label="fold to report" dimColor onPress={toggleRun} />
        </Box>
      ) : null}
    </Box>
  )
}

// MAWS draws this channel itself when it advertises native support; the
// terminal keeps this view. Every hook awaits the same read for this worker.
let maws: Promise<boolean> | undefined
const native = async ($: EngineInterface, e: object) =>
  (await (maws ??= $.env.get('MAWS_NATIVE_TO_HUMAN').then((value) => value !== undefined && value !== ''))) &&
  (!('surface' in e) || e.surface !== 'terminal')

/**
 * Registers the view. Nothing changes until the first marked assistant
 * message of the session, so a session without the output style draws as
 * the engine does; from then on, assistant messages fold to their marks and
 * the working record (unmarked messages, tool calls and their results) folds
 * behind buttons, until a row is unfolded by its button or the whole
 * transcript by the band above the prompt. Agent spawns and their failures
 * stay in the report, and so does an API error that ends the turn; agent
 * messages, finish notifications and other sessions' messages are working
 * record.
 */
export function registerToHuman(on: On) {
  let hasSeenMark = false
  let isFullTranscript = false
  const view = newView(() => hasSeenMark && !isFullTranscript)
  const { unfolded, isFolding } = view

  // Where each row stands in the transcript (see `View`). A resumed or forked
  // session's rows are read from its file, which can be far past what one read
  // takes whole, so a search lists them; one that fails, or is cut, leaves the
  // rows it could not place to draw in the order they come. A cleared or
  // resumed session's rows are another transcript's: what the view knew of the
  // one before is dropped, and the rows still drawn are asked for again.
  on('classic.SessionStart', { source: /^/ }, async ($, e, next) => {
    if (e.source === 'clear' || e.source === 'resume' || e.source === 'fork') {
      view.order.length = 0
      view.rowOf.clear()
      view.place.clear()
      view.guess.clear()
      unfolded.clear()
      $.ui.invalidate('ui.render')
    }
    if (e.source === 'resume' || e.source === 'fork') {
      try {
        const search = await $.process.run(placeArgs(e.transcript_path))
        // grep: 0 found, 1 none, anything else a failure.
        if (search.exitCode > 1) {
          throw new Error(`grep exited ${search.exitCode}`)
        }
        placeAll(view, placesIn(search.stdout))
        if (reorder(view) && isFolding()) {
          $.ui.invalidate('ui.render')
        }
      } catch (error) {
        $.ui.log(`to-human: the transcript's order could not be read (${String(error)}); its runs follow the order rows draw in`, { to: 'debug' })
      }
    }
    return next(e)
  })

  // Each row the main conversation keeps, as its append resolves: placed
  // after every row before it, its tool calls with it. A row that drew while
  // it streamed, before its place was known, moves to it.
  on('session.append', { door: /./ }, async ($, e, next) => {
    const stored = await next(e)
    if (e.agentId === undefined && e.door !== 'queue' && stored.deny === undefined) {
      try {
        view.appended += 1
        const calls = stored.message.content.flatMap((block) => (block.type === 'tool_use' && typeof block.id === 'string' ? [block.id] : []))
        const ids = [stored.uuid, ...calls]
        placeAll(view, ids, LIVE + view.appended, 1 / 1000)
        if (ids.some((id) => view.rowOf.has(id) || view.rowOf.has(GROUP + id)) && reorder(view) && isFolding()) {
          $.ui.invalidate('ui.render')
        }
      } catch (error) {
        // The row is kept whatever this hook makes of it; only its place is lost.
        $.ui.log(`to-human: an appended row could not be placed (${String(error)})`, { to: 'debug' })
      }
    }
    return stored
  })

  // Where the engine expands a group itself (`--verbose`, the ctrl+o
  // transcript) each call is a row of its own: which group's run a call's
  // row stands in, and which call is a group's last, whose row draws the
  // run's end in the group's place.
  const groupOf = new Map<string, string>()
  const lastOf = new Map<string, string>()

  // The ids of the Agent and Workflow calls the transcript drew, whose
  // failure notifications stay in the report as the spawns do.
  const spawns = new Set<string>()

  // An API error that ends a turn (retries spent, the context limit) is an
  // assistant message the engine writes, drawn through the same row as the
  // model's text, and the model never answers after it: nothing it could
  // send would tell the person, so the row stays in the report. The row's
  // props do not say it is an error; `turn.complete` does, and the
  // transcript's last assistant message is its text.
  const errors = new Set<string>()
  on('turn.complete', { reason: 'error' }, async ($, e, next) => {
    if (e.agentId === undefined) {
      const text = (await $.session.messages()).findLast((message) => message.role === 'assistant')?.text.trim()
      if (text !== undefined && text !== '' && !errors.has(text)) {
        errors.add(text)
        $.ui.invalidate('ui.render')
      }
    }
    return next(e)
  })

  // The person's prompt breaks a run: the record before it and the record
  // after it are two, as the person reads them. Agent messages and background
  // deliveries are working record, and stand in the run they fall in.
  on('ui.render', { component: 'UserMessage' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    const kind = promptRow(e.props, spawns)
    see($, view, e.requestId, kind)
    return isFolding() && kind === 'record' ? recordRow($, e, next, view) : next(e)
  })

  // The line that closes a turn (`Baked for 3s`, `Waiting for N background
  // agents to finish`) is working record, but never a row of a run: a run it
  // started would have no row to draw its button. It is drawn only while
  // the run of the row before it is unfolded, where it is read as the
  // transcript's footer of that stretch; otherwise it draws nothing, and the
  // full transcript shows it as the engine does. The row before it is the
  // drawn row placed last before it, or, while its place is unknown, the row
  // drawn last when it first drew.
  const before = new Map<string, string | undefined>()
  on('ui.render', { component: 'TurnDuration' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    if (!before.has(e.requestId)) {
      before.set(e.requestId, view.order[view.order.length - 1])
    }
    if (!isFolding()) {
      return next(e)
    }
    const prior = view.place.has(e.requestId) ? view.order[slotOf(view, e.requestId) - 1] : before.get(e.requestId)
    const isShown =
      prior !== undefined && inRun(view.rowOf.get(prior)) && unfolded.has(runStart(view.order, view.rowOf, prior))
    if (isShown) {
      return next(e)
    }
    const { Box } = $.ui.resolve(e)
    return <Box />
  })

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    const parsed = parse(e.props.text)
    const isError = parsed.spans.length === 0 && errors.has(e.props.text.trim())
    see($, view, e.requestId, parsed.spans.length === 0 && !isError ? 'record' : parsed.hasRecord ? 'mixed' : 'marked')

    if (parsed.spans.length > 0 && !hasSeenMark) {
      // Rows drawn before the first mark (the tool rows of this turn, the
      // band) are cached; ask for them again now that the view folds.
      hasSeenMark = true
      $.ui.invalidate('ui.render')
    }

    if (!isFolding() || isError) {
      return next(e)
    }

    const bullet = e.props.isFirstOfReply ? '● ' : '  '

    if (parsed.spans.length === 0) {
      return recordRow($, e, next, view, { bullet })
    }

    const { Box, Text, Button, Markdown } = $.ui.resolve(e)
    const requestId = e.requestId
    const toggleThis = () => toggle(unfolded, requestId)

    // Unfolded, a mixed message is the first row of its run: the run's end
    // draws the fold, under itself, unless the run is this row alone.
    if (unfolded.has(requestId)) {
      return (
        <Box flexDirection="column">
          {await next(e)}
          {runEnd(view.order, view.rowOf, requestId) === requestId ? (
            <Box paddingLeft={2}>
              <Button key={TOGGLE} label="fold to report" dimColor onPress={toggleThis} />
            </Box>
          ) : null}
        </Box>
      )
    }

    const last = parsed.spans.length - 1

    // A span's body is markdown as the model wrote it (a table, a list, a
    // code fence), drawn as the surface draws a reply's text (see
    // `markdownBlocks`), directly under its label. The bullet is the engine's
    // two-column gutter, so the body is padded by as much to sit where the
    // transcript's text does. The row stands one line below the row above,
    // as the engine's rows do.
    // On the terminal its file links open in VS Code (see `fileLinks`).
    const bodies = parsed.spans.map((span, i) => (
      <Box flexDirection="column">
        {markdownBlocks(span.text).map((block, j) => {
          if (e.surface !== 'terminal') return <Markdown text={block} />
          const { text, targets } = fileLinks(block)
          return targets.length === 0 ? (
            <Markdown text={text} />
          ) : (
            <Markdown key={`${LINKS}${i}:${j}`} text={text} onLinkPress={() => {}} pressableLinks={targets.slice(0, 256)} />
          )
        })}
      </Box>
    ))

    return (
      <Box flexDirection="column" marginTop={1}>
        {parsed.spans.map((span, i) => {
          const style = STYLE[span.kind]
          return (
            <Box flexDirection="column" marginBottom={i < last ? 1 : 0}>
              <Box>
                <Text color={style.color} bold>
                  {i === 0 ? bullet : '  '}
                  {style.label}
                  {span.isOpen ? ' …' : ''}
                </Text>
              </Box>
              <Box paddingLeft={2}>{bodies[i]}</Box>
            </Box>
          )
        })}
        {parsed.hasRecord ? (
          // The one button of this message's record and of the run after it.
          <Box paddingLeft={2} marginTop={1}>
            <Button key={TOGGLE} label="working record" dimColor onPress={toggleThis} />
          </Box>
        ) : null}
      </Box>
    )
  })

  // A tool call is working record too, and stands in the run it falls in,
  // except one the person reads: the question dialog's, whose row is the
  // answer they gave, and an agent spawn; each breaks the run as a marked
  // message does. A standalone call's
  // result is a row of its own beneath it once the call resolves, so until
  // then (no output, and no abort, which leaves one) the call's row is the
  // last of the two. A row of a group the engine expanded draws its output
  // inline and is whole: it stands in the group's run, and the group's last
  // call draws the run's end where the group would.
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    const read = isRead(e.props.tool)
    if (isSpawn(e.props.tool)) {
      spawns.add(e.props.tool_use_id)
    }
    const group = groupOf.get(e.requestId)
    if (group === undefined) {
      see($, view, e.requestId, read ? 'marked' : 'record')
    }
    if (!isFolding() || read) {
      return next(e)
    }
    if (group !== undefined) {
      return recordRow($, e, next, view, { id: group, opens: false, closes: lastOf.get(group) === e.requestId })
    }
    return recordRow($, e, next, view, { closes: e.props.output === undefined && !e.props.isInterrupted })
  })

  // A group's own id changes while it forms, so the row is known by its
  // first call's, which does not. Unfolded, the group draws as the
  // transcript does, one count line: each call in its place would be the
  // ctrl+o form, its whole output inline. Where the engine expands it
  // itself (`--verbose`, the ctrl+o transcript) each call is a row of its
  // own that finds the group's run by `groupOf`, never through the order: a
  // group expands and collapses as the view changes, and a call added to
  // the order late would land after rows that drew since, or stay in it
  // with no row to draw once the group collapses again. The last call
  // draws the run's end in the group's place, and when a call joins the
  // group the row that drew it is asked for again.
  on('ui.render', { component: 'ToolGroup' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    const id = `${GROUP}${e.props.calls[0]?.tool_use_id ?? e.requestId}`
    see($, view, id, 'record')
    let last: string | undefined
    for (const call of e.props.calls) {
      if (call.tool_use_id) {
        groupOf.set(call.tool_use_id, id)
        last = call.tool_use_id
        if (isSpawn(call.tool)) {
          spawns.add(call.tool_use_id)
        }
      }
    }
    if (last !== undefined && lastOf.get(id) !== last) {
      const moved = lastOf.has(id)
      lastOf.set(id, last)
      if (moved && e.props.isExpanded && isFolding() && unfolded.has(runStart(view.order, view.rowOf, id))) {
        $.ui.invalidate('ui.render')
      }
    }
    return isFolding() ? recordRow($, e, next, view, { id, closes: !e.props.isExpanded }) : next(e)
  })

  // The result row shares its call's id: folded, the call's row has drawn
  // the run's button and this one draws nothing; unfolded, it is the last
  // of the two, and carries the run's end.
  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    const read = isRead(e.props.tool)
    see($, view, e.requestId, read ? 'marked' : 'record')
    return isFolding() && !read ? recordRow($, e, next, view, { opens: false }) : next(e)
  })

  // The band above the prompt names the view and switches it: the whole
  // transcript as the engine draws it, or the report. Its line goes under
  // what the hooks beneath draw there (the ask's open questions), which this
  // plugin's hooks sit outside of.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    if (!hasSeenMark || e.props.hasSurvey) {
      return next(e)
    }

    const inner = await next(e)
    const { Box, Text, Button } = $.ui.resolve(e)

    return (
      <Box flexDirection="column">
        {inner}
        <Box marginTop={1}>
          <Text dimColor>to-human view · </Text>
          <Button
            key={MODE}
            label={isFullTranscript ? 'report only' : 'full transcript'}
            dimColor
            onPress={() => {
              isFullTranscript = !isFullTranscript
            }}
          />
        </Box>
      </Box>
    )
  })

  // A press runs the button's own closure beneath this hook; the redraw
  // follows it so the transcript reflects the state the closure left.
  on('ui.press', { element: TOGGLE }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    const result = await next(e)
    $.ui.invalidate('ui.render')
    return result
  })

  on('ui.press', { element: MODE }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    const result = await next(e)
    $.ui.invalidate('ui.render')
    return result
  })

  // A plain click on a span's file link opens it in VS Code, at its line.
  on('ui.press', { element: /^to-human-links:/ }, async ($, e, next) => {
    const url = e.link === undefined ? undefined : editorUrl(e.link.href)
    if (url !== undefined) {
      const opened = await $.process.run(['open', url]).catch(() => undefined)
      if (opened?.exitCode !== 0) $.ui.toast(`could not open ${url} in VS Code`)
    }
    return next(e)
  })
}
