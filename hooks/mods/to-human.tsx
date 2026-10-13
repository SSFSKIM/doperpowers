import type { EngineInterface, On, PromptOrigin, RenderElement, RenderInput } from 'claude-code'

import { ASK_TOOL } from './ask'

/**
 * The marks the `to-human` output style asks the model to write: a message
 * to the human, what the model needs from them, and an explanatory insight.
 * The old `to-human` and `essential` marks read as messages too. Everything
 * outside a mark is the model's working record.
 */
export type Kind = 'message' | 'need-input' | 'insight'

/**
 * One option a `need-input` mark offers, as a `<choice>` line under the
 * question; `recommended` when the model marked it the one it would pick.
 */
export type Choice = {
  text: string
  recommended: boolean
}

export type Span = {
  kind: Kind
  text: string
  /** True while the closing tag has not arrived: the span is still streaming. */
  isOpen: boolean
  /** The options of a `need-input` span, lifted out of its text; absent when it offers none. */
  choices?: Choice[]
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

/** Raw choices use the same flat, code-aware tag pairing as MAWS grammar 2. */
const CHOICE_TAG = /<choice(?: recommended)?>|<\/choice>/g

function liftRawChoices(span: Span, inCode: (offset: number) => boolean, start: number) {
  if (span.kind !== 'need-input') return
  const choices: Choice[] = []
  const marks = [...span.text.matchAll(CHOICE_TAG)].filter((mark) => !inCode(start + mark.index))
  const opens: number[] = []
  const flat: [RegExpExecArray, RegExpExecArray][] = []
  for (let i = 0; i < marks.length; i++) {
    if (marks[i]![0] !== '</choice>') opens.push(i)
    else if (opens.length > 0) {
      const open = opens.pop()!
      // Nested or malformed choice markup is not a flat option; keep it literal.
      if (opens.length === 0 && i === open + 1) flat.push([marks[open]!, marks[i]!])
    }
  }
  let text = ''
  let from = 0
  for (const [open, close] of flat) {
    const body = span.text.slice(open.index + open[0].length, close.index).trim()
    if (body !== '') choices.push({ text: body, recommended: open[0] !== '<choice>' })
    text += span.text.slice(from, open.index)
    from = close.index + close[0].length
    if (span.text[from] === '\n') from++
  }
  span.text = text + span.text.slice(from)
  if (choices.length > 0) span.choices = choices
}

/**
 * A choice as the streaming hook drew it: text under `◇`, or `◆` for the
 * recommended one, running to the next marker or the end of its line (the
 * hook breaks the line before a marker, but a model may write two choices
 * on one line, and this reads the text the hook was given either way).
 */
const MARKER = /([◇◆]) ([^\n]*?)(?=\s*[◇◆] |\n|$)/g

/**
 * Lifts the choices out of a `need-input` span's text, in the form
 * `pattern` gives them, leaving the question. A span of another kind keeps
 * its text as it is.
 */
function liftChoices(
  span: Span,
  pattern: RegExp,
  isRecommended: (mark: string | undefined) => boolean,
  inCode: (offset: number) => boolean = insideCode(codeRegions(span.text)),
  start = 0,
) {
  if (span.kind !== 'need-input') {
    return
  }
  const choices: Choice[] = []
  span.text = span.text.replace(pattern, (whole: string, mark: string | undefined, text: string, offset: number) => {
    // A rendered marker needs only its start outside code: the option's body
    // may end in backticks. Raw choices are paired separately, token by token.
    if (inCode(start + offset)) {
      return whole
    }
    const trimmed = text.trim()
    if (trimmed !== '') {
      choices.push({ text: trimmed, recommended: isRecommended(mark) })
    }
    return ''
  })
  if (choices.length > 0) {
    span.choices = choices
  }
}

/**
 * Splits text still carrying its marks. Marks may nest (an `<insight>`
 * inside a `<message>`): each contiguous run of text under one mark is a
 * span of its own, in the order written. An unclosed mark runs to the end.
 */
function parseMarked(text: string): Parsed {
  let reading = readingOf(text, codeRegions(text))
  if (!reading.balanced) {
    const glued = readingOf(text, regionsOf(text, GLUED))
    if (glued.balanced) reading = glued
  }
  const { inCode, tokens } = reading
  const starts = new Map<Span, number>()
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
      starts.set(top.span, last)
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
    const kind = (tag === 'to-human' || tag === 'essential' ? 'message' : tag) as Kind
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
      starts.set(span, last)
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
    liftRawChoices(span, inCode, starts.get(span) ?? 0)
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
 * mark's label in its own bold color, a dimmed run is working record.
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
  '35': 'need-input',
  '33': 'insight',
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
    liftChoices(span, MARKER, (mark) => mark === '◆')
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
 * agent's dispatch); a mixed row, a message
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

/** The props of a prompt row that say what it is. */
export type PromptRowProps = {
  origin?: Pick<PromptOrigin, 'kind'>
  /** Present when someone other than the person sent it: an agent, a teammate, another session, a channel. */
  from?: { name: string }
  /** Present on a notification row: the background task it reports on, an agent's run among them. */
  task?: { id?: string; toolUseId?: string }
}

/**
 * The person's own words stay visible. Messages delivered by agents and
 * background notifications belong to the working record.
 */
export function promptRow(props: PromptRowProps): RowKind {
  if (props.from !== undefined || props.task !== undefined) {
    return 'record'
  }
  return props.origin !== undefined && DELIVERED.has(props.origin.kind) ? 'record' : 'user'
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
 * A question the model asked through a `need-input` mark: `id` names the
 * span (its message and its place in it), `head` is the line an answer
 * quotes, `choices` what it offered.
 */
export type Question = {
  id: string
  head: string
  choices: Choice[]
}

const HEAD_MAX = 120

function cut(text: string, max: number): string {
  const points = Array.from(text)
  return points.length >= max ? `${points.slice(0, max - 1).join('')}…` : text
}

/**
 * The line an answer quotes to name its question: the question's first
 * non-blank line, with double quotes replaced before it is cut so the answer
 * form has one unambiguous closing quote.
 */
export function questionHead(text: string): string {
  const line = (text.split('\n').map((l) => l.trim()).find((l) => l !== '') ?? '').replace(/"/g, "'")
  return cut(line, HEAD_MAX)
}

/**
 * The prompt an answer is: the question's head, then the answer, so the
 * model reads which question it settles without a table to look it up in,
 * and a reader of the transcript sees the same. `answerOf` reads it back,
 * from a prompt a click submitted or one the person typed after `reply`
 * put the head in their box.
 */
export function answerText(head: string, answer: string): string {
  return `Answering "${head}": ${answer}`
}

/**
 * An answer's line, wherever it stands in the prompt, one per question
 * answered; what the person wrote on other lines is theirs and not echoed.
 * A head carries no double quote, so the first `":` closes it and the
 * answer may hold anything.
 */
const ANSWER = /^Answering "([^"\n]*)": ?(.*)$/gm

export type Answer = { head: string; answer: string }

/** Every answer a prompt carries, in the order of its lines. */
export function answersOf(text: string): Answer[] {
  return Array.from(text.matchAll(ANSWER), (match) => ({
    head: match[1] as string,
    answer: (match[2] as string).trim(),
  }))
}

/**
 * The prompt box after a press, so the answers to several questions go in
 * one prompt: each question has at most one line. Every line answering
 * `head` (a duplicate the person pasted or edited in included, which would
 * otherwise settle the question by the later line) gives way to one: the
 * choice pressed, where the first of them stood, or, when the press is
 * `reply` (no `answer`), the answer's opening at the end, where the cursor
 * is for the person to finish it; a question with no line yet gets one at
 * the end. Every other line, the other answers and whatever the person
 * typed, stays as it is.
 */
export function withAnswer(box: string, head: string, answer?: string): string {
  const line = answerText(head, answer ?? '')
  const lines = box.trim() === '' ? [] : box.split('\n')
  const answers = (l: string) => answersOf(l)[0]?.head === head
  const at = lines.findIndex(answers)
  const kept = lines.filter((l) => !answers(l))
  if (answer !== undefined && at >= 0) {
    kept.splice(at, 0, line)
    return kept.join('\n')
  }
  if (kept[kept.length - 1] === '') {
    kept.pop()
  }
  kept.push(line)
  return kept.join('\n')
}

/**
 * A remote surface (the desktop app, VS Code, mobile) draws a span's body as
 * its own `Markdown`. A render answer carries one props, so of several blocks
 * handed back beneath the hook only the first can draw there: Claude Desktop
 * portals its native row into the first `engine` node and draws nothing at
 * the rest, which left every span after the first label-only and a
 * `need-input` question with buttons and no question (2026-10-03). The
 * terminal draws the hook's whole tree in-process, so there the body stays
 * the engine's own drawing. `Markdown.text` takes at most 10000 characters
 * and no control character but tab and newline.
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

const STYLE: Record<Kind, { label: string; color: string }> = {
  message: { label: 'message', color: 'claude' },
  'need-input': { label: 'need input', color: 'magenta' },
  insight: { label: 'insight', color: 'yellow' },
}

const TOGGLE = 'to-human-toggle'
const MODE = 'to-human-mode'
const ASK = 'need-input:'

/**
 * What a press on one of a question's buttons does: writes a choice as the
 * answer in the person's box, or writes the answer's opening for them to
 * finish.
 */
type Press = { kind: 'answer'; question: Question; answer: string } | { kind: 'reply'; question: Question }

/** Questions (the built-in's and the ask mod's) and agent spawns stay in the report; messaging is working record. */
export const isRead = (tool: string) => tool === 'AskUserQuestion' || tool === ASK_TOOL || tool === 'Agent' || tool === 'Workflow'

/**
 * What the view keeps between draws: the rows unfolded by a button (a marked
 * message by its own, a run of working record by the one button that stands
 * for it, keyed by the row the run starts at), and the order the transcript's
 * rows first drew in with what each one is.
 */
type View = {
  unfolded: Set<string>
  order: string[]
  rowOf: Map<string, RowKind>
  /** Whether the view folds now: a mark has been seen and the whole transcript is not asked for. */
  isFolding: () => boolean
}

/**
 * Notes a row as it draws: its place in the order rows first drew, and what
 * it is. The row an open run ends at draws its `[ fold to report ]`; a row
 * that joins the run, or that turns from record into one closing it, moves
 * that end, and the row that drew the button (or should now) is cached as
 * it was: the rows are asked for again.
 */
function see($: EngineInterface, view: View, requestId: string, kind: RowKind) {
  const { order, rowOf, unfolded } = view
  const known = rowOf.get(requestId)
  if (known === kind) {
    return
  }
  if (known === undefined) {
    order.push(requestId)
  }
  rowOf.set(requestId, kind)
  const before = order[order.indexOf(requestId) - 1]
  if (view.isFolding() && before !== undefined && inRun(rowOf.get(before)) && unfolded.has(runStart(order, rowOf, before))) {
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

const noop = () => {}

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
      <Box>
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

/**
 * Reads the answers the transcript holds into `answered`: every prompt of
 * the person's that names its questions, the latest per question.
 */
async function readAnswers($: EngineInterface, answered: Map<string, string>) {
  for (const message of await $.session.messages()) {
    if (message.role !== 'user') {
      continue
    }
    for (const { head, answer } of answersOf(message.text)) {
      answered.set(head, answer)
    }
  }
}

// MAWS draws this channel itself when it advertises native support; the
// terminal keeps this view. Every hook awaits the same read for this worker.
// The prompt-submit hook is not gated: it draws nothing, and the terminal's
// view reads the answers it settles.
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
 * transcript by the band above the prompt. Agent spawns stay in the report;
 * agent messages and finish notifications are working record. A `need-input` span draws its
 * choices as buttons under the question, in the message itself.
 */
export function registerToHuman(on: On) {
  let hasSeenMark = false
  let isFullTranscript = false
  const view: View = { unfolded: new Set(), order: [], rowOf: new Map(), isFolding: () => hasSeenMark && !isFullTranscript }
  const { unfolded, isFolding } = view

  // The answers the transcript holds, by the question's head, and what
  // each question button does, by its key.
  const answered = new Map<string, string>()
  const presses = new Map<string, Press>()
  let hasReadTranscript = false

  // Where the engine expands a group itself (`--verbose`, the ctrl+o
  // transcript) each call is a row of its own: which group's run a call's
  // row stands in, and which call is a group's last, whose row draws the
  // run's end in the group's place.
  const groupOf = new Map<string, string>()
  const lastOf = new Map<string, string>()

  const keyOf = (question: Question, press: Press) => {
    const key = `${ASK}${question.id}:${press.kind === 'answer' ? question.choices.findIndex((c) => c.text === press.answer) : press.kind}`
    presses.set(key, press)
    return key
  }

  // The person's prompt breaks a run: the record before it and the record
  // after it are two, as the person reads them. Agent messages and background
  // deliveries are working record, and stand in the run they fall in.
  on('ui.render', { component: 'UserMessage' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    const kind = promptRow(e.props)
    see($, view, e.requestId, kind)
    return isFolding() && kind === 'record' ? recordRow($, e, next, view) : next(e)
  })

  // The line that closes a turn (`Baked for 3s`, `Waiting for N background
  // agents to finish`) is working record, but never a row of a run: a run it
  // started would have no row to draw its button. It is drawn only while
  // the run of the row before it is unfolded, where it is read as the
  // transcript's footer of that stretch; otherwise it draws nothing, and the
  // full transcript shows it as the engine does.
  const before = new Map<string, string | undefined>()
  on('ui.render', { component: 'TurnDuration' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    if (!before.has(e.requestId)) {
      before.set(e.requestId, view.order[view.order.length - 1])
    }
    if (!isFolding()) {
      return next(e)
    }
    const prior = before.get(e.requestId)
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
    see($, view, e.requestId, parsed.spans.length === 0 ? 'record' : parsed.hasRecord ? 'mixed' : 'marked')

    if (parsed.spans.length > 0 && !hasSeenMark) {
      // Rows drawn before the first mark (the tool rows of this turn, the
      // band) are cached; ask for them again now that the view folds.
      hasSeenMark = true
      $.ui.invalidate('ui.render')
    }

    // The questions this message asks, each once it is whole.
    const asked = parsed.spans.map((span, i): Question | undefined =>
      span.kind !== 'need-input' || span.isOpen
        ? undefined
        : { id: `${e.requestId}:${i}`, head: questionHead(span.text), choices: span.choices ?? [] },
    )
    if (!hasReadTranscript && asked.some((question) => question !== undefined)) {
      // A resumed session's answers are in its transcript: read them once,
      // the first time a question draws.
      hasReadTranscript = true
      await readAnswers($, answered)
    }

    if (!isFolding()) {
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
    // code fence). On the terminal it is drawn by the engine: the block is
    // handed back beneath this hook with the span's text in place of the
    // whole, and no bullet, since the label above carries it. The bullet is
    // the engine's two-column gutter, so the body is padded by as much to sit
    // where the transcript's text does. A remote surface draws it as its own
    // `Markdown` instead, one block per span, since only the first block
    // handed back would draw there (see `markdownBlocks`).
    const bodies = await Promise.all(
      parsed.spans.map((span) =>
        e.surface === 'terminal'
          ? next({ ...e, props: { ...e.props, text: span.text, isFirstOfReply: false } })
          : Promise.resolve(
              <Box flexDirection="column">
                {markdownBlocks(span.text).map((block) => (
                  <Markdown text={block} />
                ))}
              </Box>,
            ),
      ),
    )

    return (
      <Box flexDirection="column">
        {parsed.spans.map((span, i) => {
          const style = STYLE[span.kind]
          const question = asked[i]
          const answer = question ? answered.get(question.head) : undefined
          return (
            <Box flexDirection="column" marginBottom={i < last ? 1 : 0}>
              <Box>
                <Text color={style.color} bold>
                  {i === 0 ? bullet : '  '}
                  {style.label}
                  {span.isOpen ? ' …' : ''}
                </Text>
                {answer !== undefined ? <Text dimColor> · answered: {answer}</Text> : null}
              </Box>
              <Box paddingLeft={2}>{bodies[i]}</Box>
              {question && answer === undefined ? (
                <Box flexDirection="column" paddingLeft={2}>
                  {question.choices.map((choice, n) => (
                    <Box>
                      <Button
                        key={keyOf(question, { kind: 'answer', question, answer: choice.text })}
                        label={`${n + 1}: ${choice.text}${choice.recommended ? ' ★' : ''}`}
                        onPress={noop}
                      />
                    </Box>
                  ))}
                  <Box>
                    <Button key={keyOf(question, { kind: 'reply', question })} label="reply…" dimColor onPress={noop} />
                  </Box>
                </Box>
              ) : null}
            </Box>
          )
        })}
        {parsed.hasRecord ? (
          // The one button of this message's record and of the run after it.
          <Box paddingLeft={2}>
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
    const id = `group:${e.props.calls[0]?.tool_use_id ?? e.requestId}`
    see($, view, id, 'record')
    let last: string | undefined
    for (const call of e.props.calls) {
      if (call.tool_use_id) {
        groupOf.set(call.tool_use_id, id)
        last = call.tool_use_id
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
  // transcript as the engine draws it, or the report.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (await native($, e)) return next(e)
    if (!hasSeenMark || e.props.hasSurvey) {
      return next(e)
    }

    const { Box, Text, Button } = $.ui.resolve(e)

    return (
      <Box>
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

  // A question's buttons need the engine, which their closures cannot reach:
  // the press is answered here, by what the key was drawn to do. A choice
  // and `reply` both write the person's box, the choice as the whole answer
  // and `reply` as its opening, each on a line of its own beside the
  // answers already there, so one Enter sends them all as the person's own
  // prompt. (A prompt a plugin submits enters under the plugin's name,
  // framed as the plugin's message to the model and labelled so in the
  // transcript, by an origin no hook may change; so nothing here submits.)
  on('ui.press', async ($, e, next) => {
    if (await native($, e)) return next(e)
    const press = e.element.startsWith(ASK) ? presses.get(e.element) : undefined
    if (!press) {
      return next(e)
    }
    const result = await next(e)
    const box = await $.prompt.read()
    const text = withAnswer(box.text, press.question.head, press.kind === 'answer' ? press.answer : undefined)
    const { isFilled } = await $.prompt.fill({ text })
    if (!isFilled) {
      $.ui.toast('The answer could not be put in the prompt')
    }
    return result
  })

  // An answer is a prompt that names its question, one line per question,
  // as a choice or `reply` wrote them in the box, or as the person typed
  // them; each question is settled once the prompt enters. (Not gated on
  // MAWS: a submission carries no surface, this hook draws nothing, and an
  // answer given either way is what the terminal's question reads.)
  on('prompt.submit', async ($, e, next) => {
    const found = answersOf(e.text)
    if (found.length === 0) {
      return next(e)
    }
    const result = await next(e)
    if (result.drop === undefined) {
      for (const { head, answer } of found) {
        answered.set(head, answer)
      }
      $.ui.invalidate('ui.render')
    }
    return result
  })
}
