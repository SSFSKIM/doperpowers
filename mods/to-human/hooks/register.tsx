import type { EngineInterface, On, RenderElement } from 'claude-code'

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

const TAG = /<(to-human|essential|need-input)>([\s\S]*?)(<\/\1>|$)/g

/**
 * Splits one assistant text block into its marked spans and notes whether a
 * working record surrounds them. An unclosed tag runs to the end of the text.
 */
export function parse(text: string): Parsed {
  const spans: Span[] = []
  let outside = ''
  let last = 0

  for (const match of text.matchAll(TAG)) {
    const [whole, kind, body, close] = match
    const at = match.index ?? 0
    outside += text.slice(last, at)
    last = at + whole.length
    spans.push({ kind: kind as Kind, text: (body ?? '').trim(), isOpen: close === '' })
  }

  outside += text.slice(last)

  return { spans, hasRecord: outside.trim() !== '' }
}

const STYLE: Record<Kind, { label: string; color: string }> = {
  'to-human': { label: 'to human', color: 'cyan' },
  essential: { label: 'essential', color: 'yellow' },
  'need-input': { label: 'need input', color: 'magenta' },
}

const TOGGLE = 'to-human-toggle'
const MODE = 'to-human-mode'

/**
 * An empty tree in a row's place: what a folded tool row draws.
 */
function hidden($: EngineInterface, e: Parameters<EngineInterface['ui']['resolve']>[0]): RenderElement {
  const { Box } = $.ui.resolve(e)
  return <Box />
}

/**
 * Registers the view. Nothing changes until the first marked assistant
 * message of the session, so a session without the output style draws as
 * the engine does; from then on, assistant messages fold to their marks and
 * tool rows fold away, until a message is unfolded by its button or the
 * whole transcript by the band above the prompt.
 */
export function register(on: On) {
  let hasSeenMark = false
  let isFullTranscript = false
  const unfolded = new Set<string>()

  const isFolding = () => hasSeenMark && !isFullTranscript

  const toggleMessage = (requestId: string) => {
    if (unfolded.has(requestId)) {
      unfolded.delete(requestId)
    } else {
      unfolded.add(requestId)
    }
  }

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    const parsed = parse(e.props.text)

    if (parsed.spans.length > 0 && !hasSeenMark) {
      // Rows drawn before the first mark (the tool rows of this turn, the
      // band) are cached; ask for them again now that the view folds.
      hasSeenMark = true
      $.ui.invalidate('ui.render')
    }

    if (!isFolding()) {
      return next(e)
    }

    const { Box, Text, Button } = $.ui.resolve(e)
    const requestId = e.requestId
    const toggle = () => toggleMessage(requestId)
    const bullet = e.props.isFirstOfReply ? '● ' : '  '

    if (unfolded.has(requestId)) {
      return (
        <Box flexDirection="column">
          {await next(e)}
          <Box paddingLeft={2}>
            <Button key={TOGGLE} label="fold to report" dimColor onPress={toggle} />
          </Box>
        </Box>
      )
    }

    if (parsed.spans.length === 0) {
      return (
        <Box>
          <Text dimColor>{bullet}</Text>
          <Button key={TOGGLE} label="working record" dimColor onPress={toggle} />
        </Box>
      )
    }

    const last = parsed.spans.length - 1

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
              <Box paddingLeft={2}>
                <Text wrap="wrap">{span.text}</Text>
              </Box>
            </Box>
          )
        })}
        {parsed.hasRecord ? (
          <Box paddingLeft={2}>
            <Button key={TOGGLE} label="working record" dimColor onPress={toggle} />
          </Box>
        ) : null}
      </Box>
    )
  })

  on('ui.render', { component: 'ToolUse' }, ($, e, next) => (isFolding() ? hidden($, e) : next(e)))
  on('ui.render', { component: 'ToolGroup' }, ($, e, next) => (isFolding() ? hidden($, e) : next(e)))
  on('ui.render', { component: 'ToolResult' }, ($, e, next) => (isFolding() ? hidden($, e) : next(e)))

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
