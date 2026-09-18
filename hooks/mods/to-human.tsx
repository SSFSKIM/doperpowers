import type { EngineInterface, On, RenderElement, RenderInput } from 'claude-code'

/**
 * The three marks the `to-human` output style asks the model to write:
 * what the human should read, what is essential, and what the model needs
 * from them. Everything outside a mark is the model's working record.
 */
export type Kind = 'to-human' | 'essential' | 'need-input'

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

const TAG = /<(\/?)(to-human|essential|need-input)>/g

/**
 * Splits text still carrying its marks. Marks may nest (an `<essential>`
 * inside a `<to-human>`): each contiguous run of text under one mark is a
 * span of its own, in the order written. An unclosed mark runs to the end.
 */
function parseMarked(text: string): Parsed {
  const spans: Span[] = []
  // One entry per open mark, innermost last; `span` is the entry's current
  // run of text, or null once an inner mark has interrupted it.
  const open: { kind: Kind; span: Span | null }[] = []
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

  const close = (entry: { kind: Kind; span: Span | null }) => {
    if (entry.span) {
      entry.span.isOpen = false
    }
    entry.span = null
  }

  for (const match of text.matchAll(TAG)) {
    const [whole, slash, kind] = match
    const at = match.index ?? 0
    take(text.slice(last, at))
    last = at + whole.length

    if (slash === '') {
      const top = open[open.length - 1]
      if (top) {
        close(top)
      }
      const span: Span = { kind: kind as Kind, text: '', isOpen: true }
      spans.push(span)
      open.push({ kind: kind as Kind, span })
    } else {
      const depth = open.map((entry) => entry.kind).lastIndexOf(kind as Kind)
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
 * mark's label in its own bold color, a dimmed run is working record.
 *
 * The first group is the header's color, the second a dimmed run's text.
 */
const RENDERED = /\u001b\[1;(3[356])m(?:to human|essential|need input)\u001b\[0m|\u001b\[2m([\s\S]*?)\u001b\[0m/g

const HEADER = /\u001b\[1;3[356]m(?:to human|essential|need input)\u001b\[0m/

const KIND_OF_COLOR: Record<string, Kind> = {
  '36': 'to-human',
  '33': 'essential',
  '35': 'need-input',
}

/**
 * Splits text the streaming hook already drew. A header opens a span that
 * runs to the next header; a dimmed run is record and ends the span it
 * follows, which is how a mark's close survives a form that has no closing
 * marker.
 */
function parseRendered(text: string): Parsed {
  const spans: Span[] = []
  let outside = ''
  let current: Span | null = null
  let last = 0

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
    take(text.slice(last, at))
    last = at + whole.length

    if (color !== undefined) {
      current = { kind: KIND_OF_COLOR[color] as Kind, text: '', isOpen: false }
      spans.push(current)
    } else {
      current = null
      outside += dimmed ?? ''
    }
  }

  take(text.slice(last))

  for (const span of spans) {
    span.text = span.text.trim()
  }

  return { spans: spans.filter((span) => span.text !== ''), hasRecord: outside.trim() !== '' }
}

/**
 * Splits one assistant text block into its marked spans and notes whether a
 * working record surrounds them, in whichever of the two forms the block
 * reaches the transcript in: its own marks, or the headers the streaming
 * hook drew over them.
 */
export function parse(text: string): Parsed {
  const marked = parseMarked(text)
  if (marked.spans.length > 0 || !HEADER.test(text)) {
    return marked
  }
  return parseRendered(text)
}

/**
 * What one row of the transcript is: the person's prompt, a row they read
 * (an assistant message carrying marks, a question they answered), or
 * working record (an unmarked message, a tool call and its result).
 */
export type RowKind = 'user' | 'marked' | 'record'

/**
 * The first message of the run of working record `id` belongs to: walking
 * back over the rows that are working record too and stopping at a prompt or
 * at a message that carries marks. A run of unmarked messages draws as one
 * button rather than one button each, so the report reads as a report; this
 * names the message that draws it, and the rest of the run draw nothing.
 */
export function runStart(
  order: readonly string[],
  rowOf: ReadonlyMap<string, RowKind>,
  id: string,
): string {
  let at = order.indexOf(id)
  if (at < 0) {
    return id
  }
  while (at > 0 && rowOf.get(order[at - 1] as string) === 'record') {
    at -= 1
  }
  return order[at] as string
}

const STYLE: Record<Kind, { label: string; color: string }> = {
  'to-human': { label: 'to human', color: 'cyan' },
  essential: { label: 'essential', color: 'yellow' },
  'need-input': { label: 'need input', color: 'magenta' },
}

const TOGGLE = 'to-human-toggle'
const MODE = 'to-human-mode'

/**
 * The question dialog's tool: its row in the transcript is the person's own
 * answer, which they read as they read a mark.
 */
const isAnswered = (tool: string) => tool === 'AskUserQuestion'

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
}

function toggle(unfolded: Set<string>, id: string) {
  if (unfolded.has(id)) {
    unfolded.delete(id)
  } else {
    unfolded.add(id)
  }
}

/**
 * An empty tree in a row's place: what a folded row draws.
 */
function hidden($: EngineInterface, e: RenderInput): RenderElement {
  const { Box } = $.ui.resolve(e)
  return <Box />
}

/**
 * A row of working record, drawn as its run is: folded, the row the run
 * starts at draws the one `[ working record ]` button and the rest draw
 * nothing; unfolded, the engine's own drawing of each row, under a
 * `[ fold to report ]` at the top of the run, where it stays as the run grows.
 */
async function recordRow<E extends RenderInput>(
  $: EngineInterface,
  e: E,
  next: (e: E) => Promise<RenderElement>,
  view: View,
  bullet: string,
  id: string = e.requestId,
): Promise<RenderElement> {
  const { Box, Text, Button } = $.ui.resolve(e)
  const start = runStart(view.order, view.rowOf, id)
  const isStart = start === id
  const toggleRun = () => toggle(view.unfolded, start)

  if (!view.unfolded.has(start)) {
    return isStart ? (
      <Box>
        <Text dimColor>{bullet}</Text>
        <Button key={TOGGLE} label="working record" dimColor onPress={toggleRun} />
      </Box>
    ) : (
      <Box />
    )
  }

  return (
    <Box flexDirection="column">
      {isStart ? (
        <Box paddingLeft={2}>
          <Button key={TOGGLE} label="fold to report" dimColor onPress={toggleRun} />
        </Box>
      ) : null}
      {await next(e)}
    </Box>
  )
}

/**
 * Registers the view. Nothing changes until the first marked assistant
 * message of the session, so a session without the output style draws as
 * the engine does; from then on, assistant messages fold to their marks and
 * the working record (unmarked messages, tool calls and their results) folds
 * behind buttons, until a row is unfolded by its button or the whole
 * transcript by the band above the prompt.
 */
export function registerToHuman(on: On) {
  let hasSeenMark = false
  let isFullTranscript = false
  const view: View = { unfolded: new Set(), order: [], rowOf: new Map() }
  const { unfolded, order, rowOf } = view

  const isFolding = () => hasSeenMark && !isFullTranscript

  const see = (requestId: string, kind: RowKind) => {
    if (!rowOf.has(requestId)) {
      order.push(requestId)
    }
    rowOf.set(requestId, kind)
  }

  // The prompt breaks a run: the record before it and the record after it are
  // two, as the person reads them.
  on('ui.render', { component: 'UserMessage' }, ($, e, next) => {
    see(e.requestId, 'user')
    return next(e)
  })

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    const parsed = parse(e.props.text)
    see(e.requestId, parsed.spans.length > 0 ? 'marked' : 'record')

    if (parsed.spans.length > 0 && !hasSeenMark) {
      // Rows drawn before the first mark (the tool rows of this turn, the
      // band) are cached; ask for them again now that the view folds.
      hasSeenMark = true
      $.ui.invalidate('ui.render')
    }

    if (!isFolding()) {
      return next(e)
    }

    const bullet = e.props.isFirstOfReply ? '● ' : '  '

    if (parsed.spans.length === 0) {
      return recordRow($, e, next, view, bullet)
    }

    const { Box, Text, Button } = $.ui.resolve(e)
    const requestId = e.requestId
    const toggleThis = () => toggle(unfolded, requestId)

    if (unfolded.has(requestId)) {
      return (
        <Box flexDirection="column">
          {await next(e)}
          <Box paddingLeft={2}>
            <Button key={TOGGLE} label="fold to report" dimColor onPress={toggleThis} />
          </Box>
        </Box>
      )
    }

    const last = parsed.spans.length - 1

    // A span's body is markdown as the model wrote it (a table, a list, a
    // code fence), so it is drawn by the engine: the block is handed back
    // beneath this hook with the span's text in place of the whole, and no
    // bullet, since the label above carries it. The bullet is the engine's
    // two-column gutter, so the body is padded by as much to sit where the
    // transcript's text does.
    const bodies = await Promise.all(
      parsed.spans.map((span) => next({ ...e, props: { ...e.props, text: span.text, isFirstOfReply: false } })),
    )

    return (
      <Box flexDirection="column">
        {parsed.spans.map((span, i) => {
          const style = STYLE[span.kind]
          return (
            <Box flexDirection="column" marginBottom={i < last ? 1 : 0}>
              <Text color={style.color} bold>
                {i === 0 ? bullet : '  '}
                {style.label}
                {span.isOpen ? ' …' : ''}
              </Text>
              <Box paddingLeft={2}>{bodies[i]}</Box>
            </Box>
          )
        })}
        {parsed.hasRecord ? (
          <Box paddingLeft={2}>
            <Button key={TOGGLE} label="working record" dimColor onPress={toggleThis} />
          </Box>
        ) : null}
      </Box>
    )
  })

  // A tool call is working record too, and stands in the run it falls in,
  // except the question dialog's: the answer the person gave is theirs to
  // read, and it breaks the run as a marked message does.
  on('ui.render', { component: 'ToolUse' }, ($, e, next) => {
    const answered = isAnswered(e.props.tool)
    see(e.requestId, answered ? 'marked' : 'record')
    return isFolding() && !answered ? recordRow($, e, next, view, '  ') : next(e)
  })

  // A group's own id changes while it forms, so the row is known by its
  // first call's, which does not, and its calls are seen in its order right
  // after it, so the rows it unfolds into find their run and draw no control
  // of their own. Unfolded, the record shows the calls, not the count line.
  on('ui.render', { component: 'ToolGroup' }, ($, e, next) => {
    const id = `group:${e.props.calls[0]?.tool_use_id ?? e.requestId}`
    see(id, 'record')
    for (const call of e.props.calls) {
      if (call.tool_use_id) {
        see(call.tool_use_id, 'record')
      }
    }
    if (!isFolding()) {
      return next(e)
    }
    return recordRow($, { ...e, props: { ...e.props, isExpanded: true } }, next, view, '  ', id)
  })

  // The result row shares its call's id, so the call's row has drawn the
  // run's button: this one draws only once the run is open.
  on('ui.render', { component: 'ToolResult' }, ($, e, next) => {
    const answered = isAnswered(e.props.tool)
    see(e.requestId, answered ? 'marked' : 'record')
    if (!isFolding() || answered || unfolded.has(runStart(order, rowOf, e.requestId))) {
      return next(e)
    }
    return hidden($, e)
  })

  on('ui.render', { component: 'AbovePrompt' }, ($, e, next) => {
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
    const result = await next(e)
    $.ui.invalidate('ui.render')
    return result
  })

  on('ui.press', { element: MODE }, async ($, e, next) => {
    const result = await next(e)
    $.ui.invalidate('ui.render')
    return result
  })
}
