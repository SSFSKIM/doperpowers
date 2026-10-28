import type { ApiContentBlock, EngineInterface, On, PromptOrigin, RenderElement, RenderInput, SessionAppendInput, Timer } from 'claude-code'

import { registerEdits } from './edits'
import { FINAL_ANSWER, MESSAGE_TOOL, isMadeUp, readMessage } from './message'

/**
 * The ask mod's tool, the model's one way to ask the human in an interactive
 * session, under each plugin that registered it: sminos, where it moves, and
 * doperpowers, where it was first. A transcript holds either, for good.
 */
const ASK_TOOLS: readonly string[] = ['mcp__sminos__AskUserQuestion', 'mcp__doperpowers__AskUserQuestion']

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
 * agent's dispatch, an agent's failure, an API error); a mixed row, a message
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
 * How the ask mod opens the plugin prompt that hands the model the person's
 * answer to an async question (its `deliveryText`), possibly after the
 * framing the engine stores before a plugin prompt, under either plugin that
 * submits it (`ASK_TOOLS`). It stays the person's: the ask's own row does
 * not draw the feedback a person gives with "Chat about this" or the notes
 * added to an answer, so this row carries their words whole.
 */
const ASK_DELIVERY = /^(?:The (?:sminos|doperpowers) plugin sent a message:\s*)?The human responded to your async AskUserQuestion \(call /

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
 * reads have one `› working record` between them and not two. A run of
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
 * draws the run's `‹ fold to report`, under itself, where the person is
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

/** What the view's controls lead with, as the engine's rows that unfold do (`› Message from …`). */
const UNFOLD = '›' as const
const FOLD = '‹' as const

/**
 * A control of the view drawn as the engine draws a row that unfolds: dim
 * text that the pointer brightens anywhere on its row, where a Button alone
 * is a bracketed label the pointer inverts. A Button's `hover` applies only
 * inside a keyed Box, which is the row; the Button's own key is the press's
 * address, its `label` what names it. The mark of which way it goes stands
 * before the label, or after it (`isMarkLast`) where a caption leads, as on
 * the band. `children` stand before it on the row (a bullet, a caption).
 */
function control<E extends RenderInput>(
  $: EngineInterface,
  e: E,
  { key, label, mark, isMarkLast = false, onPress, children = null }: {
    key: string
    label: string
    mark: typeof UNFOLD | typeof FOLD
    isMarkLast?: boolean
    onPress: () => void
    children?: RenderElement | null
  },
): RenderElement {
  const { Box, Button } = $.ui.resolve(e)
  return (
    <Box key={`${key}-row`}>
      {children}
      <Button key={key} label={label} plain dimColor hover={{ inverse: false, dimColor: false }} onPress={onPress}>
        {isMarkLast ? `${label} ${mark}` : `${mark} ${label}`}
      </Button>
    </Box>
  )
}

const isSpawn = (tool: string) => tool === 'Agent' || tool === 'Workflow'

/**
 * Questions (the built-in's and the ask mod's), agent spawns and the message
 * tool's messages stay in the report; other messaging (an agent's
 * `SendMessage`) is working record.
 */
export const isRead = (tool: string) => tool === 'AskUserQuestion' || ASK_TOOLS.includes(tool) || isSpawn(tool) || tool === MESSAGE_TOOL

/**
 * Whether an appended row is an API error: one the engine writes in place of
 * a response, naming `<synthetic>` as its model (observed on 2.1.306), as it
 * does for no response at all (`No response requested.`), which is no error
 * and which the transcript does not flag as one. Whether the turn ends on it
 * (retries spent, the context limit) or goes on after it (a connection lost
 * mid-response), the model never writes the person about it, so the row
 * stays in the report.
 */
function isApiError(origin: SessionAppendInput['origin'], message: { content: readonly ApiContentBlock[] }): boolean {
  if (origin.kind !== 'model' || !('model' in origin) || origin.model !== '<synthetic>') return false
  const text = message.content.map((block) => (block.type === 'text' ? block.text : '')).join('').trim()
  return text !== '' && text !== 'No response requested.'
}

/** A message tool call that sent nothing: refused, errored, or cut by an abort. */
const isUnsent = (props: { tool: string; isErrored: boolean; isInterrupted?: boolean }) =>
  props.tool === MESSAGE_TOOL && (props.isErrored || props.isInterrupted === true)

/** A row's `onScreen`: the units of it the window shows, `null` while it is out of the window. */
type Shown = { first: number; last: number; of: number } | null

/**
 * Whether a fold of the run that starts at a row can pull the view down: the
 * row is out of the window, or its top is (it shows from a unit past its
 * first). Where no `onScreen` was said (a surface that holds no row, the main
 * screen), nothing is held, so nothing can.
 */
export const isTopOut = (shown: Shown | undefined) => shown === null || (shown !== undefined && shown.first > 0)

/** Notes where a row stood in the window as it drew (`View.shown`). */
function note(view: View, id: string, props: { onScreen?: Shown }) {
  if (props.onScreen !== undefined) {
    view.shown.set(id, props.onScreen)
  }
}

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
 * transcript file when the module starts and when a session is resumed, and
 * taken from each append after; a row that draws before its place is known
 * stands after every row appended by then.
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
  /** The `requestId` the engine draws a row under, where the view knows it by another id (a group, by its first call's). */
  requestIds: Map<string, string>
  /** The run a press just folded, by its first row, which the press then brings into view if its top is out of the window. */
  folded?: string
  /** Where each row stood in the window when it last drew, as its `onScreen` said; only the fullscreen transcript says. */
  shown: Map<string, Shown>
  /** The rows that are an API error, by their ids: kept as they were appended, and read from the transcript file with the places. */
  errors: Set<string>
  /** The rows the engine kept as answered without a request (a hook's own response), read from the transcript file with the places. */
  unrequested: Set<string>
  /** The module's start-up read (`started`) while one runs; it settles once it finished or was cut short. */
  reading?: Promise<void>
  /** Settles once the start-up read finished, or the rows stopped waiting for it. */
  start: { promise: Promise<void>; settle: () => void }
  /** The read finished under a dispatch that ran on. */
  isStarted: boolean
  /** `START_WAIT_MS` ran out before the read finished: the rows draw with what is known. */
  isPastWait: boolean
  /** The timer that ends the rows' wait, set by the first row that waited. */
  deadline?: Timer
  /** Whether the view folds now: a mark has been seen and the whole transcript is not asked for. */
  isFolding: () => boolean
}

export const newView = (isFolding: () => boolean): View => {
  let settle = () => {}
  const promise = new Promise<void>((resolve) => (settle = resolve))
  return {
    unfolded: new Set(),
    order: [],
    rowOf: new Map(),
    place: new Map(),
    guess: new Map(),
    appended: 0,
    requestIds: new Map(),
    shown: new Map(),
    errors: new Set(),
    unrequested: new Set(),
    start: { promise, settle },
    isStarted: false,
    isPastWait: false,
    isFolding,
  }
}

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
 * What a transcript search lists: each row's id, a tool call's id where its
 * call is written, and the flags the engine writes on an API error's row
 * (786 of 786 on this machine, 2026-10-21) and on a response a hook answered
 * without a request (2.1.312), each of which follows that row's own id on its
 * line.
 */
const PLACES = '"uuid":"[^"]+"|"type":"tool_use","id":"[^"]+"|"isApiErrorMessage":true|"answeredWithoutRequest":true'

/**
 * The search of the file `$1` for `$2`, each match on a line of its own,
 * exiting 0 when one was found and 1 when none was: by rg where the machine
 * has it, else by grep. A long session's transcript runs to hundreds of MB,
 * where macOS's grep takes seconds (437 MB: 8.6 s; rg, 0.7 s).
 */
const SEARCH = 'search() { if command -v rg >/dev/null 2>&1; then exec rg --no-config -a -o -N --no-filename -e "$2" -- "$1"; fi; exec grep -o -E -e "$2" -- "$1"; }'

/** The search that lists a transcript's rows in its order (`PLACES`). */
export function placeArgs(path: string): string[] {
  return ['sh', '-c', `${SEARCH}; search "$1" "$2"`, 'sh', path, PLACES]
}

/**
 * The same search over the session's own transcript, found by its id under
 * the configuration's `projects/` (the engine names the file after the
 * session): what a module that starts mid-session reads, with no path to go
 * by. A session with no file yet (a new one, a fork before its first write)
 * lists no rows, as a search that finds none.
 */
export function sessionPlaceArgs(sessionId: string): string[] {
  const script = `${SEARCH}; for f in "\${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/projects/*/"$1".jsonl; do [ -f "$f" ] && search "$f" "$2"; done; exit 1`
  return ['sh', '-c', script, 'sh', sessionId, PLACES]
}

/** The ids `placeArgs`' output names, in the transcript's order. */
export function placesIn(stdout: string): string[] {
  return stdout.split('\n').flatMap((line) => {
    const id = /"(?:uuid|id)":"([^"]+)"$/.exec(line)?.[1]
    return id === undefined ? [] : [id]
  })
}

/** The ids of the rows `placeArgs`' output flags with `flag`, which follows the row's own id. */
function flaggedIn(stdout: string, flag: string): string[] {
  let row: string | undefined
  return stdout.split('\n').flatMap((line) => {
    if (line === flag) return row === undefined ? [] : [row]
    row = /^"uuid":"([^"]+)"$/.exec(line)?.[1] ?? row
    return []
  })
}

/** The ids of the rows `placeArgs`' output flags as API errors. */
export const errorsIn = (stdout: string) => flaggedIn(stdout, '"isApiErrorMessage":true')

/** The ids of the rows `placeArgs`' output flags as answered without a request. */
export const unrequestedIn = (stdout: string) => flaggedIn(stdout, '"answeredWithoutRequest":true')

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
 * draws `› working record`, whether it ends an unfolded one and draws
 * `‹ fold to report`), and the neighbour's drawing is cached as it was: the
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

/** Unfolds the run or message `id` stands for, or folds it, noting the fold for the press's hook. */
function toggle(view: View, id: string) {
  if (view.unfolded.delete(id)) {
    view.folded = id
  } else {
    view.unfolded.add(id)
  }
}

/**
 * A row of working record, drawn as its run is. Folded, the row the run
 * starts at draws the one `› working record` button and the rest draw
 * nothing. Unfolded, each row is the engine's own drawing, as the transcript
 * draws it, and the row the run ends at draws `‹ fold to report` a line
 * under it, as the rows stand apart, where the person is when they finish
 * reading.
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
  const { Box, Text } = $.ui.resolve(e)
  const start = runStart(view.order, view.rowOf, id)
  const toggleRun = () => toggle(view, start)

  if (!view.unfolded.has(start)) {
    return opens && start === id ? (
      <Box marginTop={1}>
        {control($, e, { key: TOGGLE, label: 'working record', mark: UNFOLD, onPress: toggleRun, children: <Text dimColor>{bullet}</Text> })}
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
        <Box paddingLeft={2} marginTop={1}>{control($, e, { key: TOGGLE, label: 'fold to report', mark: FOLD, onPress: toggleRun })}</Box>
      ) : null}
    </Box>
  )
}

/**
 * Places the rows a transcript search lists (see `View`), and notes which of
 * them are API errors. A transcript can be far past what one read takes
 * whole, so a search lists its rows; one that fails, or is cut, leaves the
 * rows it could not place to draw in the order they come. `signal` is the
 * dispatch's that searches: a search its abort cut short says nothing.
 */
async function place($: EngineInterface, view: View, search: string[], signal: AbortSignal) {
  try {
    const found = await $.process.run(search)
    // grep: 0 found, 1 none, anything else a failure.
    if (found.exitCode > 1) {
      throw new Error(`grep exited ${found.exitCode}`)
    }
    placeAll(view, placesIn(found.stdout))
    const errors = errorsIn(found.stdout).filter((id) => !view.errors.has(id))
    errors.forEach((id) => view.errors.add(id))
    const unrequested = unrequestedIn(found.stdout).filter((id) => !view.unrequested.has(id))
    unrequested.forEach((id) => view.unrequested.add(id))
    if ((reorder(view) || [...errors, ...unrequested].some((id) => view.rowOf.has(id))) && view.isFolding()) {
      $.ui.invalidate('ui.render')
    }
  } catch (error) {
    if (!signal.aborted) {
      $.ui.log(`to-human: the transcript's order could not be read (${String(error)}); its runs follow the order rows draw in`, { to: 'debug' })
    }
  }
}

/** Whether the conversation holds a marked assistant message, or a message sent through the tool. */
async function sentMark($: EngineInterface, signal: AbortSignal): Promise<boolean> {
  const isSent = (use: { tool: string; input: unknown; isError?: true }) =>
    use.tool === MESSAGE_TOOL && use.isError !== true && (readMessage(use.input)?.text.trim() ?? '') !== ''
  try {
    return (await $.session.messages()).some((m) => m.role === 'assistant' && (parse(m.text).spans.length > 0 || m.toolUses.some(isSent)))
  } catch (error) {
    if (!signal.aborted) {
      $.ui.log(`to-human: the conversation could not be read for a mark (${String(error)})`, { to: 'debug' })
    }
    return false
  }
}

/** Places the rows of the session's own transcript, found by its id. */
async function placeSession($: EngineInterface, view: View, signal: AbortSignal) {
  try {
    await place($, view, sessionPlaceArgs(await $.session.id()), signal)
  } catch (error) {
    if (!signal.aborted) {
      $.ui.log(`to-human: the session's id could not be read (${String(error)}); its runs follow the order rows draw in`, { to: 'debug' })
    }
  }
}

/**
 * Reads, under one dispatch, whether the session has sent a mark (`onMark`
 * runs as soon as one is found, the conversation answering well before the
 * transcript's search) and where its rows stand; false when that dispatch
 * was aborted before the read finished, which leaves it for another to make.
 * Rows that stopped waiting for it are asked for again.
 */
async function startUp($: EngineInterface, view: View, signal: AbortSignal, onMark: () => void): Promise<boolean> {
  const marked = sentMark($, signal).then((isMarked) => {
    if (isMarked) {
      onMark()
      if (view.isPastWait) {
        $.ui.invalidate('ui.render')
      }
    }
  })
  await Promise.all([marked, placeSession($, view, signal)])
  if (signal.aborted) {
    return false
  }
  if (view.isPastWait) {
    $.ui.invalidate('ui.render')
  }
  return true
}

/**
 * Begins a start-up read under the dispatch `$` and `signal` belong to. It
 * settles once the read finished, which ends every row's wait, or was cut
 * short, which leaves the next read to whoever asks.
 */
function begin($: EngineInterface, view: View, signal: AbortSignal, onMark: () => void): Promise<void> {
  const read: Promise<void> = startUp($, view, signal, onMark)
    .catch(() => false)
    .then((isRead) => {
      if (isRead) {
        view.isStarted = true
        view.deadline?.cancel()
        view.start.settle()
      }
      if (view.reading === read) {
        view.reading = undefined
      }
    })
  view.reading = read
  return read
}

/** How long the rows wait, together, for the start-up read: well inside a draw's 10 s budget. */
export const START_WAIT_MS = 3000

/** Resolves once `promise` settles or `signal` aborts, whichever comes first. */
function untilAborted(promise: Promise<unknown>, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      signal.removeEventListener('abort', done)
      resolve()
    }
    signal.addEventListener('abort', done, { once: true })
    promise.then(done, done)
  })
}

/**
 * What the module reads once, before its first answer: whether the session
 * has sent a mark, and where its rows stand. A module that starts over in a
 * running session (an update the reload applied, a `/reload-plugins`) is
 * asked about every row the transcript holds at once. Answered as the engine
 * draws them until a mark turned up, and only then folded, the rows off the
 * screen kept the engine's height: the fullscreen transcript holds a row off
 * its window at the height it last had and lets go of it as the row scrolls
 * back in at the window's top edge, where the release reads as the transcript
 * pulling the person back down. So every hook that draws waits on this read,
 * the rows keeping what they drew meanwhile, but only while its own dispatch
 * stands and for at most `START_WAIT_MS` from the first row that waited: the
 * engine holds a draw's budget at 10 s, and two draws in a row that ran on
 * past it, deaf to their signal, have it end the hooks worker and unload the
 * plugin (2.1.302, on a 437 MB transcript). Past the wait the rows draw with
 * what is known, and are asked for again once the read lands.
 * The read runs under `session.start`, which each load of the module raises,
 * and where no redraw cuts it short. A row asked about before that begins one
 * under its own dispatch, which a redraw of the row cuts short: the hooks
 * still waiting read again under their own. `$.session.messages()` starts at
 * the last compaction, so a mark sent only before one is not found.
 */
async function started($: EngineInterface, view: View, signal: AbortSignal, onMark: () => void) {
  if (view.isStarted || view.isPastWait) {
    return
  }
  view.deadline ??= $.clock.after(START_WAIT_MS, () => {
    view.isPastWait = true
    view.start.settle()
  })
  while (!view.isStarted && !view.isPastWait && !signal.aborted) {
    await untilAborted(Promise.race([view.reading ?? begin($, view, signal, onMark), view.start.promise]), signal)
  }
  // The rows that waited go on each from an answer of its own, not all in
  // one turn of the hooks worker, which would keep it from its heartbeat.
  // Only a pause: a clock that does not answer holds no row back.
  if (!signal.aborted) {
    await $.clock.now().catch(() => {})
  }
}

/**
 * Messages as the report draws them, a span's or the message tool's alike:
 * each under its label, `after` beneath them.
 *
 * A span's body is markdown as the model wrote it (a table, a list, a code
 * fence), drawn as the surface draws a reply's text (see `markdownBlocks`),
 * directly under its label. The bullet is the engine's two-column gutter, so
 * the body is padded by as much to sit where the transcript's text does. The
 * row stands one line below the row above, as the engine's rows do. On the
 * terminal its file links open in VS Code (see `fileLinks`).
 */
function spanRows<E extends RenderInput>($: EngineInterface, e: E, spans: readonly Span[], bullet: string, after: RenderElement | null = null): RenderElement {
  const { Box, Text, Markdown } = $.ui.resolve(e)
  const last = spans.length - 1
  const bodies = spans.map((span, i) => (
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
      {spans.map((span, i) => {
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
      {after}
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
 * Registers the view. Nothing changes until the session's first marked
 * assistant message, whether the module finds it in the conversation when it
 * starts or draws it later, so a session without the output style draws as
 * the engine does; from then on, assistant messages fold to their marks and
 * the working record (unmarked messages, tool calls and their results) folds
 * behind buttons, until a row is unfolded by its button or the whole
 * transcript by the band above the prompt. Agent spawns and their failures
 * stay in the report, and so does an API error, mid-turn or at its end; agent
 * messages, finish notifications and other sessions' messages are working
 * record.
 */
export function registerToHuman(on: On) {
  let hasSeenMark = false
  let isFullTranscript = false
  const view = newView(() => hasSeenMark && !isFullTranscript)
  const { unfolded, isFolding } = view

  const markSeen = () => {
    hasSeenMark = true
  }

  // Each load of the module raises this, the first and every reload: the
  // start-up read (`started`) runs here, where no redraw of a row cuts it
  // short, unless it already finished under a row's draw.
  on('session.start', async ($, e, next) => {
    if (!view.isStarted) {
      begin($, view, next.signal, markSeen)
    }
    return next(e)
  })

  // A cleared or resumed session's rows are another transcript's: what the
  // view knew of the one before is dropped, the new file's order is read, and
  // the rows still drawn are asked for again.
  on('classic.SessionStart', { source: /^/ }, async ($, e, next) => {
    if (e.source === 'clear' || e.source === 'resume' || e.source === 'fork') {
      view.order.length = 0
      view.rowOf.clear()
      view.place.clear()
      view.guess.clear()
      view.errors.clear()
      view.unrequested.clear()
      unfolded.clear()
      $.ui.invalidate('ui.render')
    }
    if (e.source !== 'resume' && e.source !== 'fork') {
      return next(e)
    }
    // The hooks beneath run while this searches: sminos' ask mod reads
    // the same transcript for the questions it draws.
    const [result] = await Promise.all([next(e), place($, view, placeArgs(e.transcript_path), next.signal)])
    return result
  })

  // Each row the main conversation keeps, as its append resolves: placed
  // after every row before it, its tool calls with it, and noted when it is
  // an API error. A row that drew while it streamed, before its place was
  // known, moves to it; one that drew before it was known for an error is
  // asked for again.
  on('session.append', { door: /./ }, async ($, e, next) => {
    const stored = await next(e)
    if (e.agentId === undefined && e.door !== 'queue' && stored.deny === undefined) {
      try {
        view.appended += 1
        const calls = stored.message.content.flatMap((block) => (block.type === 'tool_use' && typeof block.id === 'string' ? [block.id] : []))
        const ids = [stored.uuid, ...calls]
        placeAll(view, ids, LIVE + view.appended, 1 / 1000)
        const isError = isApiError(e.origin, stored.message)
        if (isError) {
          view.errors.add(stored.uuid)
        }
        const moved = ids.some((id) => view.rowOf.has(id) || view.rowOf.has(GROUP + id)) && reorder(view)
        if ((moved || (isError && view.rowOf.has(stored.uuid))) && isFolding()) {
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
  const expanded = new Set<string>()

  // The ids of the Agent and Workflow calls the transcript drew, whose
  // failure notifications stay in the report as the spawns do.
  const spawns = new Set<string>()

  // The person's prompt breaks a run: the record before it and the record
  // after it are two, as the person reads them. Agent messages and background
  // deliveries are working record, and stand in the run they fall in.
  on('ui.render', { component: 'UserMessage' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    await started($, view, next.signal, markSeen)
    const kind = promptRow(e.props, spawns)
    note(view, e.requestId, e.props)
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
    await started($, view, next.signal, markSeen)
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

  // The response the message mod makes up after a final message stands for
  // no text of the model's: in either view it draws nothing and stands in no
  // run, as the message's result row draws nothing. It is known by where it
  // came from (the mod's own record of it, or the engine's flag on a row read
  // from the file) and by its exact text, so a model that writes the same
  // sentence is drawn as ever.
  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    await started($, view, next.signal, markSeen)
    if (isMadeUp(e.requestId, e.props.text) || (view.unrequested.has(e.requestId) && e.props.text.trim() === FINAL_ANSWER)) {
      const { Box } = $.ui.resolve(e)
      return <Box />
    }
    const parsed = parse(e.props.text)
    const isError = view.errors.has(e.requestId)
    note(view, e.requestId, e.props)
    see($, view, e.requestId, isError ? 'marked' : parsed.spans.length === 0 ? 'record' : parsed.hasRecord ? 'mixed' : 'marked')

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

    const { Box } = $.ui.resolve(e)
    const requestId = e.requestId
    const toggleThis = () => toggle(view, requestId)

    // Unfolded, a mixed message is the first row of its run: the run's end
    // draws the fold, under itself, unless the run is this row alone.
    if (unfolded.has(requestId)) {
      return (
        <Box flexDirection="column">
          {await next(e)}
          {runEnd(view.order, view.rowOf, requestId) === requestId ? (
            <Box paddingLeft={2} marginTop={1}>{control($, e, { key: TOGGLE, label: 'fold to report', mark: FOLD, onPress: toggleThis })}</Box>
          ) : null}
        </Box>
      )
    }

    return spanRows(
      $,
      e,
      parsed.spans,
      bullet,
      parsed.hasRecord ? (
        // The one button of this message's record and of the run after it.
        <Box paddingLeft={2} marginTop={1}>
          {control($, e, { key: TOGGLE, label: 'working record', mark: UNFOLD, onPress: toggleThis })}
        </Box>
      ) : null,
    )
  })

  // The message tool's calls that sent nothing (refused, errored, cut by an
  // abort), by their ids: their rows, the call's and its result's, stand in
  // the working record as the engine draws them. The result row cannot say
  // it was cut, so it reads what its call's row said.
  const unsent = new Set<string>()

  // A tool call is working record too, and stands in the run it falls in,
  // except one the person reads: the question dialog's, whose row is the
  // answer they gave, an agent spawn, and a message sent through the tool;
  // each breaks the run as a marked message does. A standalone call's
  // result is a row of its own beneath it once the call resolves, so until
  // then (no output, and no abort, which leaves one) the call's row is the
  // last of the two. A row of a group the engine expanded draws its output
  // inline and is whole: it stands in the group's run, and the group's last
  // call draws the run's end where the group would, live or not: its calls
  // finish in any order, and the pill names the first one running. A
  // standalone call still running, and a collapsed group still live, under
  // the engine's pill (`ctrl+b to run in background`) leave the run's end to
  // the pill, which draws it beneath itself: drawn by the row, the end would
  // stand between the row and its pill.
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    await started($, view, next.signal, markSeen)
    if (isUnsent(e.props)) {
      unsent.add(e.props.tool_use_id)
    }
    const read = isRead(e.props.tool) && !unsent.has(e.props.tool_use_id)
    // A message sent through the tool draws as a span does, under its label,
    // and turns the view on as a span does. While its input streams the row
    // draws the text so far, or nothing until some has arrived. The full
    // transcript draws it so too: the engine's row is the call's input as one
    // dim, cut line, where the message would be lost among the tool calls.
    if (read && e.props.tool === MESSAGE_TOOL && groupOf.get(e.requestId) === undefined) {
      const message = readMessage(e.props.input)
      const text = message?.text.trim() ?? ''
      note(view, e.requestId, e.props)
      see($, view, e.requestId, 'marked')
      if (text !== '' && !hasSeenMark) {
        hasSeenMark = true
        $.ui.invalidate('ui.render')
      }
      if (text === '') {
        const { Box } = $.ui.resolve(e)
        return <Box />
      }
      return spanRows($, e, [{ kind: 'message', text, isOpen: message?.isWhole !== true }], '● ')
    }
    if (isSpawn(e.props.tool)) {
      spawns.add(e.props.tool_use_id)
    }
    const group = groupOf.get(e.requestId)
    if (group === undefined) {
      note(view, e.requestId, e.props)
      see($, view, e.requestId, read ? 'marked' : 'record')
    }
    if (!isFolding() || read) {
      return next(e)
    }
    if (group !== undefined) {
      return recordRow($, e, next, view, { id: group, opens: false, closes: lastOf.get(group) === e.requestId })
    }
    return recordRow($, e, next, view, { closes: e.props.output === undefined && !e.props.isInterrupted && !(e.props.isRunning && pills.has(e.requestId)) })
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
    await started($, view, next.signal, markSeen)
    const id = `${GROUP}${e.props.calls[0]?.tool_use_id ?? e.requestId}`
    view.requestIds.set(id, e.requestId)
    if (e.props.isExpanded) {
      expanded.add(id)
    } else {
      expanded.delete(id)
    }
    note(view, id, e.props)
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
    return isFolding() ? recordRow($, e, next, view, { id, closes: !e.props.isExpanded && !(e.props.isActive && pills.has(id)) }) : next(e)
  })

  // The rows the engine's pill has drawn under, by the view's id for the row
  // (a group's, for a call in one): while the row is live, the pill draws
  // the run's end beneath itself, and a pill that first draws asks the row
  // to draw again without it. An expanded group's last call draws its end.
  const pills = new Set<string>()
  on('ui.render', { component: 'ToolProgress' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    await started($, view, next.signal, markSeen)
    const id = groupOf.get(e.props.tool_use_id) ?? e.props.tool_use_id
    if (expanded.has(id)) {
      return next(e)
    }
    if (!pills.has(id)) {
      pills.add(id)
      if (isFolding()) {
        $.ui.invalidate('ui.render')
      }
    }
    const drawn = await next(e)
    if (!isFolding() || !inRun(view.rowOf.get(id))) {
      return drawn
    }
    const start = runStart(view.order, view.rowOf, id)
    if (!unfolded.has(start) || runEnd(view.order, view.rowOf, id) !== id) {
      return drawn
    }
    const { Box } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        {drawn}
        <Box paddingLeft={2} marginTop={1}>{control($, e, { key: TOGGLE, label: 'fold to report', mark: FOLD, onPress: () => toggle(view, start) })}</Box>
      </Box>
    )
  })

  // The result row shares its call's id: folded, the call's row has drawn
  // the run's button and this one draws nothing; unfolded, it is the last
  // of the two, and carries the run's end.
  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    await started($, view, next.signal, markSeen)
    if (isUnsent(e.props)) {
      unsent.add(e.props.tool_use_id)
    }
    const read = isRead(e.props.tool) && !unsent.has(e.props.tool_use_id)
    see($, view, e.requestId, read ? 'marked' : 'record')
    if (read && e.props.tool === MESSAGE_TOOL) {
      // The call's row is the message, in either view; "sent" is for the model.
      const { Box } = $.ui.resolve(e)
      return <Box />
    }
    return isFolding() && !read ? recordRow($, e, next, view, { opens: false }) : next(e)
  })

  // The band above the prompt names the view and switches it: the whole
  // transcript as the engine draws it, or the report. Its line goes under
  // what the hooks beneath draw there (the ask's open questions), which this
  // plugin's hooks sit outside of.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    await started($, view, next.signal, markSeen)
    if (!hasSeenMark || e.props.hasSurvey) {
      return next(e)
    }

    const inner = await next(e)
    const { Box, Text } = $.ui.resolve(e)

    return (
      <Box flexDirection="column">
        {inner}
        <Box marginTop={1}>
          {control($, e, {
            key: MODE,
            label: isFullTranscript ? 'report only' : 'full transcript',
            mark: UNFOLD,
            isMarkLast: true,
            onPress: () => {
              isFullTranscript = !isFullTranscript
            },
            children: <Text dimColor>to-human view · </Text>,
          })}
        </Box>
      </Box>
    )
  })

  // A press runs the button's own closure beneath this hook; the redraw
  // follows it so the transcript reflects the state the closure left. A fold
  // of a run whose first row has its top out of the window then brings that
  // row into view. The person presses `‹ fold to report` at the run's end,
  // so the run's rows above the window fold while off it, where the
  // fullscreen transcript holds each at the height it had and lets go of it as
  // it scrolls back in at the window's top edge, the transcript jumping down
  // by as much each time; with the run's first row in the window, every row
  // that folds stands in it or below it. A run whose first row's top is in the
  // window is left where it is: any reveal, even one that moves nothing, stops
  // the transcript following new output at its bottom.
  on('ui.press', { element: TOGGLE }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    view.folded = undefined
    const result = await next(e)
    $.ui.invalidate('ui.render')
    const folded = view.folded
    view.folded = undefined
    if (folded !== undefined && e.surface === 'terminal' && isTopOut(view.shown.get(folded))) {
      const shown = await $.ui.scroll({ to: { requestId: view.requestIds.get(folded) ?? folded }, block: 'nearest' })
      if (shown.deny !== undefined) {
        $.ui.log(`to-human: the folded run's button could not be brought into view (${shown.deny})`, { to: 'debug' })
      }
    }
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

  // The summary lines of file changes, beneath every hook above, so they draw
  // wherever the view hands a row on to be drawn as the engine would.
  registerEdits(on, view, () => hasSeenMark)
}
