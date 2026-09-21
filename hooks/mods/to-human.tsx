import type { EngineInterface, On, RenderElement, RenderInput } from 'claude-code'

/**
 * The three marks the `to-human` output style asks the model to write:
 * what the human should read, what is essential, and what the model needs
 * from them. Everything outside a mark is the model's working record.
 */
export type Kind = 'to-human' | 'essential' | 'need-input'

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

const TAG = /<(\/?)(to-human|essential|need-input)>/g

/** A choice as the model writes it, inside a `need-input` mark. */
const CHOICE = /<choice( recommended)?>([\s\S]*?)<\/choice>\n?/g

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
function liftChoices(span: Span, pattern: RegExp, isRecommended: (mark: string | undefined) => boolean) {
  if (span.kind !== 'need-input') {
    return
  }
  const choices: Choice[] = []
  span.text = span.text.replace(pattern, (_, mark: string | undefined, text: string) => {
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
    liftChoices(span, CHOICE, (mark) => mark !== undefined)
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
const RENDERED = /\[1;(3[356])m(?:to human|essential|need input)\[0m|\[2m([\s\S]*?)\[0m/g

const HEADER = /\[1;3[356]m(?:to human|essential|need input)\[0m/

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
    liftChoices(span, MARKER, (mark) => mark === '◆')
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
 * The answer's line, wherever it stands in the prompt; what the person
 * wrote after it on further lines is theirs and not echoed. A head carries
 * no double quote, so the first `":` closes it and the answer may hold anything.
 */
const ANSWER = /^Answering "([^"\n]*)": ?(.*)$/m

export function answerOf(text: string): { head: string; answer: string } | undefined {
  const match = ANSWER.exec(text)
  if (!match) {
    return undefined
  }
  return { head: match[1] as string, answer: (match[2] as string).trim() }
}

const STYLE: Record<Kind, { label: string; color: string }> = {
  'to-human': { label: 'to human', color: 'cyan' },
  essential: { label: 'essential', color: 'yellow' },
  'need-input': { label: 'need input', color: 'magenta' },
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
  if (view.isFolding() && before !== undefined && rowOf.get(before) === 'record' && unfolded.has(runStart(order, rowOf, before))) {
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
 * the person's that names its question, the latest per question.
 */
async function readAnswers($: EngineInterface, answered: Map<string, string>) {
  for (const message of await $.session.messages()) {
    const found = message.role === 'user' ? answerOf(message.text) : undefined
    if (found) {
      answered.set(found.head, found.answer)
    }
  }
}

/**
 * Registers the view. Nothing changes until the first marked assistant
 * message of the session, so a session without the output style draws as
 * the engine does; from then on, assistant messages fold to their marks and
 * the working record (unmarked messages, tool calls and their results) folds
 * behind buttons, until a row is unfolded by its button or the whole
 * transcript by the band above the prompt. A `need-input` span draws its
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

  // The prompt breaks a run: the record before it and the record after it are
  // two, as the person reads them.
  on('ui.render', { component: 'UserMessage' }, ($, e, next) => {
    see($, view, e.requestId, 'user')
    return next(e)
  })

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    const parsed = parse(e.props.text)
    see($, view, e.requestId, parsed.spans.length > 0 ? 'marked' : 'record')

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
          <Box paddingLeft={2}>
            <Button key={TOGGLE} label="working record" dimColor onPress={toggleThis} />
          </Box>
        ) : null}
      </Box>
    )
  })

  // A tool call is working record too, and stands in the run it falls in,
  // except the question dialog's: the answer the person gave is theirs to
  // read, and it breaks the run as a marked message does. A standalone
  // call's result is a row of its own beneath it once the call resolves, so
  // until then (no output, and no abort, which leaves one) the call's row
  // is the last of the two. A row of a group the engine expanded draws its
  // output inline and is whole: it stands in the group's run, and the
  // group's last call draws the run's end where the group would.
  on('ui.render', { component: 'ToolUse' }, ($, e, next) => {
    const answered = isAnswered(e.props.tool)
    const group = groupOf.get(e.requestId)
    if (group === undefined) {
      see($, view, e.requestId, answered ? 'marked' : 'record')
    }
    if (!isFolding() || answered) {
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
  on('ui.render', { component: 'ToolGroup' }, ($, e, next) => {
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
  on('ui.render', { component: 'ToolResult' }, ($, e, next) => {
    const answered = isAnswered(e.props.tool)
    see($, view, e.requestId, answered ? 'marked' : 'record')
    return isFolding() && !answered ? recordRow($, e, next, view, { opens: false }) : next(e)
  })

  // The band above the prompt names the view and switches it: the whole
  // transcript as the engine draws it, or the report.
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

  // A question's buttons need the engine, which their closures cannot reach:
  // the press is answered here, by what the key was drawn to do. A choice
  // and `reply` both write the person's box, the choice as the whole answer
  // and `reply` as its opening; Enter sends it as the person's own prompt.
  // (A prompt a plugin submits enters under the plugin's name, framed as
  // the plugin's message to the model and labelled so in the transcript, by
  // an origin no hook may change; so nothing here submits.)
  on('ui.press', async ($, e, next) => {
    const press = e.element.startsWith(ASK) ? presses.get(e.element) : undefined
    if (!press) {
      return next(e)
    }
    const result = await next(e)
    const text = answerText(press.question.head, press.kind === 'answer' ? press.answer : '')
    const { isFilled } = await $.prompt.fill({ text })
    if (!isFilled) {
      $.ui.toast('The answer could not be put in the prompt')
    }
    return result
  })

  // An answer is a prompt that names its question, as a choice or `reply`
  // wrote it in the box, or as the person typed it; the question is settled
  // once the prompt enters.
  on('prompt.submit', async ($, e, next) => {
    const found = answerOf(e.text)
    if (!found) {
      return next(e)
    }
    const result = await next(e)
    if (result.drop === undefined) {
      answered.set(found.head, found.answer)
      $.ui.invalidate('ui.render')
    }
    return result
  })
}
