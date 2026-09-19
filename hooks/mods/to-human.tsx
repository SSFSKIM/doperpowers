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

function sameChoices(a: readonly Choice[], b: readonly Choice[]): boolean {
  return a.length === b.length && a.every((choice, i) => choice.text === b[i]?.text && choice.recommended === b[i]?.recommended)
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
 * A question the model asked through a `need-input` mark: `id` names the
 * span (its message and its place in it), `head` is the line an answer
 * quotes, `choices` what it offered.
 */
export type Question = {
  id: string
  requestId: string
  head: string
  /** The question as written, its choices lifted out: what the queue shows on request. */
  body: string
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

/**
 * The questions still open, in the order they were asked: what the queue
 * pane lists. `questions` is every question in the order it drew.
 */
export function openQuestions(
  questions: readonly Question[],
  answered: ReadonlyMap<string, string>,
  dismissed: ReadonlySet<string>,
): Question[] {
  return questions.filter((question) => !answered.has(question.head) && !dismissed.has(question.head))
}

/**
 * The question the band above the prompt shows: the newest still open.
 */
export function pending(
  questions: readonly Question[],
  answered: ReadonlyMap<string, string>,
  dismissed: ReadonlySet<string>,
): Question | undefined {
  const open = openQuestions(questions, answered, dismissed)
  return open[open.length - 1]
}

const STYLE: Record<Kind, { label: string; color: string }> = {
  'to-human': { label: 'to human', color: 'cyan' },
  essential: { label: 'essential', color: 'yellow' },
  'need-input': { label: 'need input', color: 'magenta' },
}

const TOGGLE = 'to-human-toggle'
const MODE = 'to-human-mode'
const ASK = 'need-input:'
/** The queue pane's id, and the band button that opens and closes it. */
const PANE = 'need-input'
const QUEUE = 'need-input:queue'
/** How much of a question's head a button or the band shows: a label does not wrap or cut. */
const LABEL_MAX = 60

function label(head: string): string {
  return cut(head, LABEL_MAX)
}

/**
 * What a press on one of a question's buttons does: writes a choice as the
 * answer in the person's box, writes the answer's opening for them to
 * finish, takes the question off the band, or shows its body in the queue.
 */
type Press =
  | { kind: 'answer'; question: Question; answer: string }
  | { kind: 'reply'; question: Question }
  | { kind: 'dismiss'; question: Question }
  | { kind: 'show'; question: Question }

/**
 * What the queue pane draws from: the questions still open, which of them
 * show their body, and the key each button is drawn under.
 */
type Queue = {
  open: Question[]
  shown: ReadonlySet<string>
  keyOf: (question: Question, press: Press) => string
}

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

const noop = () => {}

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
 * The queue pane: every open question in the order asked, each with its
 * choices and the same `reply…` and `dismiss` its row and the band have,
 * so one is answered from here as from there. The head is a button that
 * shows the question as written under it, for the context a cut head lacks;
 * the engine scrolls no transcript for a plugin, so the context comes to
 * the pane instead of the pane leading to it.
 */
function drawQueue($: EngineInterface, e: RenderInput<'Pane'>, queue: Queue): RenderElement {
  const { Box, Text, Button } = $.ui.resolve(e)

  if (queue.open.length === 0) {
    return <Text dimColor>no open questions</Text>
  }

  return (
    <Box flexDirection="column">
      {queue.open.map((question, i) => {
        // A question its label shows whole has nothing more to show.
        const hasMore = question.body.trim() !== label(question.head)
        const isShown = hasMore && queue.shown.has(question.id)
        return (
          <Box key={`q:${question.id}`} flexDirection="column" marginTop={i > 0 ? 1 : 0}>
            <Box>
              <Text color="magenta" bold>
                {hasMore ? (isShown ? '▾ ' : '▸ ') : '● '}
              </Text>
              {hasMore ? (
                <Button key={queue.keyOf(question, { kind: 'show', question })} label={label(question.head)} onPress={noop} />
              ) : (
                <Text wrap="truncate">{label(question.head)}</Text>
              )}
            </Box>
            {isShown ? (
              <Box paddingLeft={2}>
                <Text wrap="wrap">{question.body}</Text>
              </Box>
            ) : null}
            <Box flexDirection="column" paddingLeft={2}>
              {question.choices.map((choice, n) => (
                <Box>
                  <Button
                    key={queue.keyOf(question, { kind: 'answer', question, answer: choice.text })}
                    label={`${n + 1}: ${choice.text}${choice.recommended ? ' ★' : ''}`}
                    onPress={noop}
                  />
                </Box>
              ))}
              <Box>
                <Button key={queue.keyOf(question, { kind: 'reply', question })} label="reply…" dimColor onPress={noop} />
                <Text> </Text>
                <Button key={queue.keyOf(question, { kind: 'dismiss', question })} label="dismiss" dimColor onPress={noop} />
              </Box>
            </Box>
          </Box>
        )
      })}
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
 * choices as buttons, and the newest question still open is repeated in the
 * band, where a digit answers it from an empty prompt.
 */
export function registerToHuman(on: On) {
  let hasSeenMark = false
  let isFullTranscript = false
  const view: View = { unfolded: new Set(), order: [], rowOf: new Map() }
  const { unfolded, order, rowOf } = view

  // The questions asked so far, in the order they drew; the answers the
  // transcript holds, by the question's head; the questions taken off the
  // band; and what each question button does, by its key.
  const questions = new Map<string, Question>()
  const answered = new Map<string, string>()
  const dismissed = new Set<string>()
  const presses = new Map<string, Press>()
  let hasReadTranscript = false
  // The queue pane: whether it is open, and the questions showing their body.
  let isQueueOpen = false
  const shown = new Set<string>()

  const open = () => openQuestions([...questions.values()], answered, dismissed)

  const isFolding = () => hasSeenMark && !isFullTranscript

  const see = (requestId: string, kind: RowKind) => {
    if (!rowOf.has(requestId)) {
      order.push(requestId)
    }
    rowOf.set(requestId, kind)
  }

  const keyOf = (question: Question, press: Press) => {
    const key = `${ASK}${question.id}:${press.kind === 'answer' ? question.choices.findIndex((c) => c.text === press.answer) : press.kind}`
    presses.set(key, press)
    return key
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

    // Questions are known whatever the view shows; a new one changes what
    // the band shows, which was drawn before it.
    const asked = parsed.spans.map((span, i): Question | undefined => {
      if (span.kind !== 'need-input' || span.isOpen) {
        return undefined
      }
      const id = `${e.requestId}:${i}`
      const question = {
        id,
        requestId: e.requestId,
        head: questionHead(span.text),
        body: span.text,
        choices: span.choices ?? [],
      }
      // The band and the queue drew before this question, or before its
      // text and choices were whole: ask again when it is new or either changes.
      const known = questions.get(id)
      questions.set(id, question)
      if (!known || known.body !== question.body || !sameChoices(known.choices, question.choices)) {
        $.ui.invalidate('ui.render')
      }
      return question
    })
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

  // The band repeats the newest open question above the prompt, its choices
  // on digit hotkeys, so it is answered from an empty prompt without a scroll
  // back to the row; it stays until answered or dismissed.
  on('ui.render', { component: 'AbovePrompt' }, ($, e, next) => {
    if (!hasSeenMark || e.props.hasSurvey) {
      return next(e)
    }

    const { Box, Text, Button } = $.ui.resolve(e)
    const opened = open()
    const question = opened[opened.length - 1]

    return (
      <Box flexDirection="column">
        {question ? (
          <Box flexDirection="column">
            <Box>
              <Text color="magenta" bold>
                need input
              </Text>
              <Text dimColor> · </Text>
              <Text wrap="truncate">{label(question.head)}</Text>
              <Text dimColor> · </Text>
              <Button key={QUEUE} label={`${opened.length} open`} dimColor onPress={noop} />
            </Box>
            <Box>
              {question.choices.map((choice, n) => (
                <Box marginRight={2}>
                  <Button
                    key={keyOf(question, { kind: 'answer', question, answer: choice.text })}
                    label={`${choice.text}${choice.recommended ? ' ★' : ''}`}
                    plain
                    {...(n < 9 ? { hotkey: String(n + 1) } : {})}
                    onPress={noop}
                  />
                </Box>
              ))}
              <Box marginRight={2}>
                <Button key={keyOf(question, { kind: 'reply', question })} label="reply…" dimColor onPress={noop} />
              </Box>
              <Button key={keyOf(question, { kind: 'dismiss', question })} label="dismiss" dimColor onPress={noop} />
            </Box>
          </Box>
        ) : null}
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
    const { question } = press
    if (press.kind === 'dismiss') {
      dismissed.add(question.head)
      $.ui.invalidate('ui.render')
    } else if (press.kind === 'show') {
      toggle(shown, question.id)
      $.ui.invalidate('ui.render')
    } else {
      const text = answerText(question.head, press.kind === 'answer' ? press.answer : '')
      const { isFilled } = await $.prompt.fill({ text })
      if (!isFilled) {
        $.ui.toast('The answer could not be put in the prompt')
      }
    }
    return result
  })

  // The queue pane lists every open question; the band's count button opens
  // and closes it, and the person's own close (its mark, ctrl+x x) is noted.
  on('ui.render', { component: 'Pane', requestId: PANE }, ($, e) => {
    // Drawn only while open: so a module reloaded under an open pane knows.
    isQueueOpen = true
    return drawQueue($, e, { open: open(), shown, keyOf })
  })

  on('ui.press', { element: QUEUE }, async ($, e, next) => {
    const result = await next(e)
    if (isQueueOpen) {
      isQueueOpen = false
      await $.ui.close({ id: PANE })
    } else {
      await $.ui.open({ id: PANE, title: 'need input' })
      isQueueOpen = true
    }
    return result
  })

  on('ui.close', { id: PANE }, ($, e, next) => {
    isQueueOpen = false
    return next(e)
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
