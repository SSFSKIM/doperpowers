import { describe, expect, mock, test, tier } from 'claude-code/testing'

import type { RowKind } from '../../hooks/mods/to-human'
import {
  answerText,
  answersOf,
  isRead,
  markdownBlocks,
  parse,
  promptRow,
  questionHead,
  runEnd,
  runStart,
  withAnswer,
} from '../../hooks/mods/to-human'

tier('user')

describe('register', () => {
  test('parse splits marked spans from the working record', async () => {
    const parsed = parse(
      'Reading the file.\n<message>Done.</message>\n<insight>Tests fail.</insight>',
    )

    expect(parsed.spans).toEqual([
      { kind: 'message', text: 'Done.', isOpen: false },
      { kind: 'insight', text: 'Tests fail.', isOpen: false },
    ])
    expect(parsed.hasRecord).toBe(true)
  })

  test('parse reads old to-human marks as messages', async () => {
    const parsed = parse('<to-human>Done.</to-human>\nWorking.')

    expect(parsed.spans).toEqual([{ kind: 'message', text: 'Done.', isOpen: false }])
    expect(parsed.hasRecord).toBe(true)
  })

  test('parse reads old essential marks as messages', async () => {
    const parsed = parse('<essential>Tests fail.</essential>\nWorking.')

    expect(parsed.spans).toEqual([{ kind: 'message', text: 'Tests fail.', isOpen: false }])
    expect(parsed.hasRecord).toBe(true)
  })

  test('parse closes nested aliases by the tag the model wrote', async () => {
    const parsed = parse('<to-human>Done.\n<essential>Tests fail.</to-human>\nWorking.')

    expect(parsed.spans).toEqual([
      { kind: 'message', text: 'Done.', isOpen: false },
      { kind: 'message', text: 'Tests fail.', isOpen: false },
    ])
    expect(parsed.hasRecord).toBe(true)
  })

  test('parse leaves an unclosed span open while it streams', async () => {
    const parsed = parse('<need-input>Which branch')

    expect(parsed.spans).toEqual([{ kind: 'need-input', text: 'Which branch', isOpen: true }])
    expect(parsed.hasRecord).toBe(false)
  })

  test('parse lifts a mark nested inside another into a span of its own', async () => {
    const parsed = parse(
      '<message>\nDone.\n\n<insight>\nTests fail.\n</insight>\nMore.\n</message>',
    )

    expect(parsed.spans).toEqual([
      { kind: 'message', text: 'Done.', isOpen: false },
      { kind: 'insight', text: 'Tests fail.', isOpen: false },
      { kind: 'message', text: 'More.', isOpen: false },
    ])
    expect(parsed.hasRecord).toBe(false)
  })

  test('parse does not let an unclosed mark swallow the marks after it', async () => {
    const parsed = parse('<message>Done.\n<insight>Tests fail.</insight>\n<need-input>Which')

    expect(parsed.spans).toEqual([
      { kind: 'message', text: 'Done.', isOpen: false },
      { kind: 'insight', text: 'Tests fail.', isOpen: false },
      { kind: 'need-input', text: 'Which', isOpen: true },
    ])
  })

  // Captured from a live session: what the transcript holds once
  // to-human-stream.sh has drawn the marks while the message streamed.
  const streamed =
    'Notes: formatting-only request, no tools needed.\n\n\n' +
    '\u001b[1;36mto human\u001b[0m\n\n\nRivers carry water downhill.\n\n\n' +
    '\u001b[1;32messential\u001b[0m\n\n\nNo files were changed.\n\n\n' +
    '\u001b[2mDone \u2014 nothing else pending.\u001b[0m\n'

  test('parse reads the old headers the streaming hook drew as messages', async () => {
    const parsed = parse(streamed)

    expect(parsed.spans).toEqual([
      { kind: 'message', text: 'Rivers carry water downhill.', isOpen: false },
      { kind: 'message', text: 'No files were changed.', isOpen: false },
    ])
    expect(parsed.hasRecord).toBe(true)
  })

  test('parse ends a span at the record that follows it', async () => {
    const parsed = parse(
      '\u001b[1;36mmessage\u001b[0m\n\nKept.\n\u001b[2mDropped from the span.\u001b[0m\n',
    )

    expect(parsed.spans).toEqual([{ kind: 'message', text: 'Kept.', isOpen: false }])
    expect(parsed.hasRecord).toBe(true)
  })

  test('parse reads an insight as a span of its own, in either form', async () => {
    expect(parse('Editing.\n<insight>The cache key is the path.</insight>').spans).toEqual([
      { kind: 'insight', text: 'The cache key is the path.', isOpen: false },
    ])
    expect(parse('\u001b[1;33minsight\u001b[0m\n\nThe cache key is the path.\n').spans).toEqual([
      { kind: 'insight', text: 'The cache key is the path.', isOpen: false },
    ])
  })

  test('parse finds no spans in an unmarked message', async () => {
    const parsed = parse('Plain reply.')

    expect(parsed.spans).toEqual([])
    expect(parsed.hasRecord).toBe(true)
  })
})

// Golden MessageDisplay output: the record's SGR sequences interrupt the
// fence lines and literal tags, but do not change their code meaning.
const renderedFenceRecord = (fence: string, close: boolean, blank = false) =>
  '\n\u001b[1;38;2;215;119;87mmessage\u001b[0m\n\nReport.\n' +
  `\u001b[2m${fence}\u001b[0m\n` + (blank ? '\n' : '') +
  '\u001b[2m<need-input>\u001b[0m\u001b[2mExample</need-input>\u001b[0m\n' +
  (close ? `\u001b[2m${fence}\u001b[0m\n` : '')

describe('tags in code', () => {
  const sentence = 'The style now asks for three marks: `<message>`, `<need-input>`, `<insight>`.'

  test('rendered headers win over literal raw tags in ANSI-dimmed fenced record', async () => {
    for (const [fence, close, blank] of [['~~~', true, false], ['```', true, true], ['```', false, true]] as const) {
      expect(parse(renderedFenceRecord(fence, close, blank))).toEqual({
        spans: [{ kind: 'message', text: 'Report.', isOpen: false }], hasRecord: true,
      })
    }
  })

  test('rendered headers quoted in fenced or inline code remain part of the real message', async () => {
    const quoted = '\u001b[1;35mneed input\u001b[0m'
    for (const example of [`~~~\n<need-input>Example</need-input>\n${quoted}\n~~~`, `Use \`${quoted}\` literally.`]) {
      const body = `Example:\n${example}\nDone.`
      expect(parse(`\u001b[1;38;2;215;119;87mmessage\u001b[0m\n\n${body}`)).toEqual({
        spans: [{ kind: 'message', text: body, isOpen: false }], hasRecord: false,
      })
    }
    expect(parse(`~~~\n${quoted}\n~~~`)).toEqual({ spans: [], hasRecord: true })
    expect(parse(`<message>Use \`${quoted}\` literally.</message>`)).toEqual({
      spans: [{ kind: 'message', text: `Use \`${quoted}\` literally.`, isOpen: false }], hasRecord: false,
    })
  })

  test('quoted vocabulary is working record, not three empty reports', async () => {
    expect(parse(sentence)).toEqual({ spans: [], hasRecord: true })
  })

  test('a real message keeps its backticked vocabulary without nested marks', async () => {
    expect(parse(`<message>${sentence}</message>`)).toEqual({
      spans: [{ kind: 'message', text: sentence, isOpen: false }], hasRecord: false,
    })
  })

  test('fenced questions and choices are literal, with either fence character', async () => {
    for (const fence of ['```', '~~~~']) {
      const example = `${fence}md\n<need-input>Which?\n<choice recommended>A</choice>\n<choice>B</choice>\n</need-input>\n${fence}`
      expect(parse(example)).toEqual({ spans: [], hasRecord: true })
      expect(parse(`<message>Example:\n${example}\nDone.</message>`)).toEqual({
        spans: [{ kind: 'message', text: `Example:\n${example}\nDone.`, isOpen: false }], hasRecord: false,
      })
    }
  })

  test('quoted closers and choice tags do not end a mark or become buttons', async () => {
    const question = 'Which form?\nWrite `<choice>A</choice>` lines.\n```\n</need-input>\n<choice>B</choice>\n```'
    expect(parse(`<need-input>${question}\n<choice recommended>Yes</choice>\n</need-input>`)).toEqual({
      spans: [{ kind: 'need-input', text: question, isOpen: false, choices: [{ text: 'Yes', recommended: true }] }],
      hasRecord: false,
    })
  })

  test('fences close only with the same character and sufficient length, or run to the end', async () => {
    expect(parse('````\n```\n~~~~\n<message>quoted</message>\n````\n<message>Shown.</message>')).toEqual({
      spans: [{ kind: 'message', text: 'Shown.', isOpen: false }], hasRecord: true,
    })
    expect(parse('Intro\n```\n<message>quoted</message>')).toEqual({ spans: [], hasRecord: true })
  })

  test('inline spans pair equal-length runs within a paragraph, skipping unpaired other lengths', async () => {
    for (const text of ['Use ``a ` <message>x</message>`` ok', '```<message>x</message>```', 'Use ``` x `` <message>x</message> ``']) {
      expect(parse(text)).toEqual({ spans: [], hasRecord: true })
    }
    for (const text of ['A stray ` then <message>Done.</message>', 'A ` start\n\n<message>Done.</message> and ` end']) {
      expect(parse(text)).toEqual({ spans: [{ kind: 'message', text: 'Done.', isOpen: false }], hasRecord: true })
    }
  })

  test('JavaScript line terminators in fence info leave the line in its inline paragraph', async () => {
    for (const info of ['\r', ' ', ' ']) {
      expect(parse(`Use \`\n<need-input>Example</need-input>\n~~~${info}\n x\`\n`)).toEqual({ spans: [], hasRecord: true })
    }
  })

  test('JavaScript trim whitespace ends an inline-code paragraph', async () => {
    for (const blank of [' ', ' ', '\f']) {
      expect(parse(`stray \`\n${blank}\nUse \`<need-input>Example</need-input>\`\n`)).toEqual({ spans: [], hasRecord: true })
    }
  })

  test('a glued fence recovers balanced marks, but never reinterprets a balanced strict report', async () => {
    for (const fence of ['```', '~~~']) {
      expect(parse(`<message>Run this:\n${fence}bash\nnpm test\n${fence}</message>\n<need-input>Go?</need-input>`)).toEqual({
        spans: [{ kind: 'message', text: `Run this:\n${fence}bash\nnpm test\n${fence}`, isOpen: false },
          { kind: 'need-input', text: 'Go?', isOpen: false }], hasRecord: false,
      })
    }
    expect(parse('<message>```bash\nnpm test\n```\n</message>\n<need-input>Go?</need-input>').spans).toEqual([
      { kind: 'message', text: '```bash\nnpm test\n```', isOpen: false }, { kind: 'need-input', text: 'Go?', isOpen: false },
    ])
    const example = 'Example syntax:\n```text\n```</message>\n<need-input>Example only?</need-input>\n```\nEnd of example.'
    expect(parse(`<message>${example}</message>`)).toEqual({
      spans: [{ kind: 'message', text: example, isOpen: false }], hasRecord: false,
    })
  })

  test('rendered orange messages keep quoted tags and do not turn code choice markers into buttons', async () => {
    expect(parse(`\u001b[1;38;2;215;119;87mmessage\u001b[0m\n\n${sentence}\n`)).toEqual({
      spans: [{ kind: 'message', text: sentence, isOpen: false }], hasRecord: false,
    })
    expect(parse('\u001b[1;35mneed input\u001b[0m\n\nExample:\n```\n◇ literal\n```\n◆ Yes\n').spans).toEqual([
      { kind: 'need-input', text: 'Example:\n```\n◇ literal\n```', isOpen: false, choices: [{ text: 'Yes', recommended: true }] },
    ])
  })
})

describe('runStart', () => {
  const rows = (...pairs: [string, RowKind][]) => ({
    order: pairs.map(([id]) => id),
    rowOf: new Map<string, RowKind>(pairs),
  })

  test('every message of a run of working record names the run it starts at', async () => {
    const { order, rowOf } = rows(['r1', 'record'], ['r2', 'record'], ['r3', 'record'])

    expect(order.map((id) => runStart(order, rowOf, id))).toEqual(['r1', 'r1', 'r1'])
  })

  test('a prompt breaks the run', async () => {
    const { order, rowOf } = rows(['r1', 'record'], ['p', 'user'], ['r2', 'record'], ['r3', 'record'])

    expect(runStart(order, rowOf, 'r3')).toBe('r2')
  })

  test('a message carrying marks breaks the run', async () => {
    const { order, rowOf } = rows(['r1', 'record'], ['m', 'marked'], ['r2', 'record'])

    expect(runStart(order, rowOf, 'r2')).toBe('r2')
    expect(runStart(order, rowOf, 'r1')).toBe('r1')
  })

  test('a mixed message, marks with record beside them, is where the run after it starts', async () => {
    const { order, rowOf } = rows(['r1', 'record'], ['m', 'mixed'], ['r2', 'record'], ['r3', 'record'], ['n', 'mixed'])

    expect(runStart(order, rowOf, 'r1')).toBe('r1')
    expect(runStart(order, rowOf, 'm')).toBe('m')
    expect(runStart(order, rowOf, 'r2')).toBe('m')
    expect(runStart(order, rowOf, 'r3')).toBe('m')
    expect(runStart(order, rowOf, 'n')).toBe('n')
    expect(runEnd(order, rowOf, 'm')).toBe('r3')
  })

  test('a message the transcript has not drawn yet stands alone', async () => {
    const { order, rowOf } = rows(['r1', 'record'])

    expect(runStart(order, rowOf, 'unseen')).toBe('unseen')
  })
})

describe('runEnd', () => {
  const rows = (...pairs: [string, RowKind][]) => ({
    order: pairs.map(([id]) => id),
    rowOf: new Map<string, RowKind>(pairs),
  })

  test('every message of a run of working record names the row it ends at', async () => {
    const { order, rowOf } = rows(['r1', 'record'], ['r2', 'record'], ['r3', 'record'])

    expect(order.map((id) => runEnd(order, rowOf, id))).toEqual(['r3', 'r3', 'r3'])
  })

  test('a prompt, and a message carrying marks, end the run before them', async () => {
    const { order, rowOf } = rows(['r1', 'record'], ['p', 'user'], ['r2', 'record'], ['m', 'marked'], ['r3', 'record'])

    expect(runEnd(order, rowOf, 'r1')).toBe('r1')
    expect(runEnd(order, rowOf, 'r2')).toBe('r2')
    expect(runEnd(order, rowOf, 'r3')).toBe('r3')
  })

  test('a message the transcript has not drawn yet stands alone', async () => {
    const { order, rowOf } = rows(['r1', 'record'])

    expect(runEnd(order, rowOf, 'unseen')).toBe('unseen')
  })
})

describe('choices', () => {
  const choices = [
    { text: 'SQLite: one file, no daemon', recommended: false },
    { text: 'Postgres: already running for the board', recommended: true },
  ]

  test('parse lifts the choices out of a need-input span', async () => {
    const parsed = parse(
      '<need-input>\nWhich backend?\n<choice>SQLite: one file, no daemon</choice>\n' +
        '<choice recommended>Postgres: already running for the board</choice>\n</need-input>',
    )

    expect(parsed.spans).toEqual([{ kind: 'need-input', text: 'Which backend?', isOpen: false, choices }])
  })

  test('parse reads the choice markers the streaming hook drew', async () => {
    const parsed = parse(
      '\u001b[1;35mneed input\u001b[0m\n\nWhich backend?\n' +
        '\u25c7 SQLite: one file, no daemon\n\u25c6 Postgres: already running for the board\n',
    )

    expect(parsed.spans).toEqual([{ kind: 'need-input', text: 'Which backend?', isOpen: false, choices }])
  })

  test('raw choices pair only tag tokens outside code, ignoring quoted closing tags', async () => {
    expect(parse('<need-input>Which?\n<choice>Keep `</choice>` literal.</choice>\n</need-input>')).toEqual({
      spans: [{ kind: 'need-input', text: 'Which?', isOpen: false, choices: [
        { text: 'Keep `</choice>` literal.', recommended: false },
      ] }], hasRecord: false,
    })
  })

  test('raw choices ignore fenced closing tag examples before their real closer', async () => {
    expect(parse('<need-input>Which?\n<choice recommended>Keep this example:\n```\n</choice>\n```\nliteral.</choice>\n</need-input>')).toEqual({
      spans: [{ kind: 'need-input', text: 'Which?', isOpen: false, choices: [
        { text: 'Keep this example:\n```\n</choice>\n```\nliteral.', recommended: true },
      ] }], hasRecord: false,
    })
  })

  test('nested and unclosed raw choice markup stays literal under the flat option grammar', async () => {
    const markup = '<choice>Outer <choice>Inner</choice></choice>\n<choice>Unclosed'
    expect(parse(`<need-input>Which?\n${markup}</need-input>`)).toEqual({
      spans: [{ kind: 'need-input', text: `Which?\n${markup}`, isOpen: false }], hasRecord: false,
    })
  })

  test('rendered choices may end in inline code or consist entirely of it', async () => {
    expect(parse('\u001b[1;35mneed input\u001b[0m\n\nWhich?\n◇ Use `main`\n◆ `npm test`\n')).toEqual({
      spans: [{ kind: 'need-input', text: 'Which?', isOpen: false, choices: [
        { text: 'Use `main`', recommended: false }, { text: '`npm test`', recommended: true },
      ] }], hasRecord: false,
    })
    expect(parse('<need-input>Which?\n<choice>Use `main`</choice>\n<choice recommended>`npm test`</choice>\n</need-input>')).toEqual({
      spans: [{ kind: 'need-input', text: 'Which?', isOpen: false, choices: [
        { text: 'Use `main`', recommended: false }, { text: '`npm test`', recommended: true },
      ] }], hasRecord: false,
    })
    // A raw closing choice tag inside code cannot close the real choice.
    expect(parse('<need-input>Example:\n<choice>Use `</choice>` literally.\n</need-input>')).toEqual({
      spans: [{ kind: 'need-input', text: 'Example:\n<choice>Use `</choice>` literally.', isOpen: false }], hasRecord: false,
    })
  })

  test('parse reads choices written on one line, in either form', async () => {
    const inline = [
      { text: 'SQLite', recommended: false },
      { text: 'Postgres', recommended: true },
    ]

    expect(
      parse('<need-input>Which backend? <choice>SQLite</choice> <choice recommended>Postgres</choice></need-input>').spans,
    ).toEqual([{ kind: 'need-input', text: 'Which backend?', isOpen: false, choices: inline }])
    expect(parse('[1;35mneed input[0m\n\nWhich backend? ◇ SQLite ◆ Postgres\n').spans).toEqual([
      { kind: 'need-input', text: 'Which backend?', isOpen: false, choices: inline },
    ])
  })

  test('a choice outside a need-input span is text', async () => {
    const parsed = parse('<message>\nPick.\n<choice>A</choice>\n</message>')

    expect(parsed.spans).toEqual([{ kind: 'message', text: 'Pick.\n<choice>A</choice>', isOpen: false }])
  })
})

describe('answers', () => {
  test('questionHead is the first line of the question, bounded', async () => {
    expect(questionHead('\nWhich backend?\nMore detail.')).toBe('Which backend?')
    expect(questionHead('Which "mode"?')).toBe("Which 'mode'?")
    expect(questionHead('x'.repeat(200))).toBe('x'.repeat(119) + '\u2026')
    expect(questionHead('x'.repeat(118) + '\ud83d\ude00y')).toBe('x'.repeat(118) + '\ud83d\ude00\u2026')
  })

  test('answerText names the question and the choice, and answersOf reads it back', async () => {
    const text = answerText('Which backend?', 'Postgres')

    expect(text).toBe('Answering "Which backend?": Postgres')
    expect(answersOf(text)).toEqual([{ head: 'Which backend?', answer: 'Postgres' }])
    expect(answersOf('Answering "Which backend?": ')).toEqual([{ head: 'Which backend?', answer: '' }])
    expect(answersOf(answerText('Which format?', 'Use "fast": mode'))).toEqual([{ head: 'Which format?', answer: 'Use "fast": mode' }])
    expect(answersOf('Just a prompt.')).toEqual([])
    // The engine frames a prompt a plugin submitted; the transcript keeps the frame.
    expect(
      answersOf('The doperpowers plugin sent a message:\nAnswering "Which backend?": Postgres\n\nThis is how Claude Code surfaces a prompt.'),
    ).toEqual([{ head: 'Which backend?', answer: 'Postgres' }])
  })

  test('answersOf reads every answer of a prompt, one per line, and leaves the other lines alone', async () => {
    const text = 'Answering "Which backend?": Postgres\nAnswering "Which region?": eu-west\nAlso: keep the old data.'

    expect(answersOf(text)).toEqual([
      { head: 'Which backend?', answer: 'Postgres' },
      { head: 'Which region?', answer: 'eu-west' },
    ])
  })

  test('withAnswer gives each question one line of the box, so two answers go in one prompt', async () => {
    const one = withAnswer('', 'Which backend?', 'Postgres')
    const two = withAnswer(one, 'Which region?', 'eu-west')

    expect(one).toBe('Answering "Which backend?": Postgres')
    expect(two).toBe('Answering "Which backend?": Postgres\nAnswering "Which region?": eu-west')
    // A second press on a question replaces its line where it stands.
    expect(withAnswer(two, 'Which backend?', 'SQLite')).toBe(
      'Answering "Which backend?": SQLite\nAnswering "Which region?": eu-west',
    )
  })

  test('withAnswer puts a reply last, where the cursor is, and keeps what the person typed', async () => {
    const typed = 'Answering "Which backend?": Postgres\nAnswering "Which region?": eu-west\nPlease keep the old data.'

    // `reply` on an answered question moves its line to the end as the opening.
    expect(withAnswer(typed, 'Which backend?', undefined)).toBe(
      'Answering "Which region?": eu-west\nPlease keep the old data.\nAnswering "Which backend?": ',
    )
    // A choice pressed after a reply was typed leaves the typed reply as it is.
    expect(withAnswer('Answering "Which backend?": my own', 'Which region?', 'eu-west')).toBe(
      'Answering "Which backend?": my own\nAnswering "Which region?": eu-west',
    )
    // A box ending in a newline takes the line without a blank one before it.
    expect(withAnswer('note to self\n', 'Which region?', 'eu-west')).toBe('note to self\nAnswering "Which region?": eu-west')
    expect(withAnswer('  ', 'Which region?', 'eu-west')).toBe('Answering "Which region?": eu-west')
  })

  test('withAnswer collapses two lines for one question into the one pressed', async () => {
    // A duplicate the person pasted or edited in would settle the question by
    // its later line, over the choice just pressed.
    const pasted = 'Answering "Q": old\nAnswering "Q": later\nnote'

    expect(withAnswer(pasted, 'Q', 'new')).toBe('Answering "Q": new\nnote')
    expect(withAnswer(pasted, 'Q', undefined)).toBe('note\nAnswering "Q": ')
  })
})

describe('promptRow', () => {
  test('a prompt the person typed, or one of unknown origin, is theirs', async () => {
    expect(promptRow({ origin: { kind: 'composer' } })).toBe('user')
    expect(promptRow({ origin: { kind: 'bridge' } })).toBe('user')
    expect(promptRow({ origin: { kind: 'unclassified' } })).toBe('user')
    expect(promptRow({})).toBe('user')
  })

  test('a delivery of the model\'s own business is working record, an agent\'s finish among them', async () => {
    expect(promptRow({ origin: { kind: 'scheduled-trigger' } })).toBe('record')
    expect(promptRow({ origin: { kind: 'coordinator' } })).toBe('record')
    // A background command's notification.
    expect(promptRow({ origin: { kind: 'task-notification' }, task: { id: 'br5d455do', toolUseId: 'toolu_1' } })).toBe('record')
    // A subagent's finish: the model reports what it returned.
    expect(promptRow({ origin: { kind: 'task-notification' }, task: { id: 'a5d804ff68753fdeb', toolUseId: 'toolu_2' } })).toBe('record')
  })

  test('received agent messages are working record, even without an origin', async () => {
    expect(promptRow({ origin: { kind: 'peer' }, from: { name: 'reviewer' } })).toBe('record')
    expect(promptRow({ origin: { kind: 'peer-send-message' }, from: { name: 'lead' } })).toBe('record')
    expect(promptRow({ from: { name: 'reviewer' } })).toBe('record')
  })
})

describe('rows', () => {
  // The plugin the runner stages the mods as.
  const PLUGIN = 'doperpowers-mods'

  test('incoming messages fold into the surrounding run and remain available when unfolded', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? e.component)],
    }))
    const message = (requestId: string, text: string) =>
      $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: true } })
    await message('m1', '<message>Checking.</message>')
    const first = await message('r1', 'Working.')
    const incoming = await $.ui.mount({
      plugin: PLUGIN,
      surface: 'terminal',
      component: 'UserMessage',
      requestId: 'peer1',
      props: { text: 'Review ready.', origin: { kind: 'peer' }, from: { name: 'reviewer' }, isExpanded: false },
    })
    const last = await message('r2', 'Reading the review.')
    await message('m2', '<message>Checked.</message>')

    expect(await first.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await incoming.find({ type: 'Text', text: 'Review ready.' })).toBeUndefined()
    expect(await incoming.find({ type: 'Button' })).toBeUndefined()
    expect(await last.find({ type: 'Button' })).toBeUndefined()
    await first.press({ key: 'to-human-toggle' })
    expect(await incoming.find({ type: 'Text', text: 'Review ready.' })).toBeDefined()
    expect(await last.find({ type: 'Button', text: 'fold to report' })).toBeDefined()
  })

  test('an agent\'s finish notification stands in the run it falls in', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    // The engine's own drawing beneath the mod: the row's text, one line.
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? e.component)],
    }))

    const message = (requestId: string, text: string) =>
      $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: true } })
    const marked1 = message('m1', '<message>One.</message>')
    const record1 = message('u1', 'Working.')
    const notification = $.ui.mount({
      plugin: PLUGIN,
      surface: 'terminal',
      component: 'UserMessage',
      requestId: 'n1',
      props: {
        text: 'Agent "Resolve the merge" finished · 5m 3s',
        origin: { kind: 'task-notification' },
        isExpanded: false,
        task: { id: 'a1', toolUseId: 'toolu_1' },
      },
    })
    const marked2 = message('m2', '<message>Two.</message>')
    const record2 = message('u2', 'More.')
    const [, first, note, , second] = await Promise.all([marked1, record1, notification, marked2, record2])

    // The first unmarked message opens the run the notification stands in; the
    // second opens the run after the second mark. The notification draws no
    // button of its own.
    expect(await first.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await second.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await note.find({ type: 'Button' })).toBeUndefined()

    // Unfolded from its first row, the run ends at the notification, which
    // draws the fold; the first row does not.
    await first.press({ key: 'to-human-toggle' })
    expect(await note.find({ type: 'Button', text: 'fold to report' })).toBeDefined()
    expect(await first.find({ type: 'Button', text: 'fold to report' })).toBeUndefined()
  })
})

describe('mixed', () => {
  const PLUGIN = 'doperpowers-mods'

  test('a marked message with record beside it draws the one button for itself and the run after it', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? e.component)],
    }))
    const message = (requestId: string, text: string) =>
      $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: true } })
    const mixed = await message('m1', 'Looking first.\n<message>One.</message>')
    const record = await message('u1', 'Working.')
    const after = await message('m2', '<message>Two.</message>')

    // One button, the mixed message's; the record row after it draws nothing.
    expect(await mixed.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await record.find({ type: 'Button' })).toBeUndefined()
    expect(await after.find({ type: 'Button' })).toBeUndefined()

    // Unfolded from the mixed message, the run ends at the record row, which
    // draws the fold; the mixed message does not.
    await mixed.press({ key: 'to-human-toggle' })
    expect(await record.find({ type: 'Button', text: 'fold to report' })).toBeDefined()
    expect(await mixed.find({ type: 'Button', text: 'fold to report' })).toBeUndefined()
  })
})

describe('surfaces', () => {
  const PLUGIN = 'doperpowers-mods'
  const TEXT =
    '<message>One.</message>\n' +
    '<need-input>Which branch?\n<choice recommended>main</choice>\n<choice>dev</choice>\n</need-input>'

  test('a remote surface draws every span body as its own Markdown, the question included', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    // The engine's own drawing beneath the mod, as the terminal case reads it.
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? e.component)],
    }))
    const ui = await $.ui.mount({
      plugin: PLUGIN,
      surface: 'desktop',
      component: 'AssistantMessage',
      requestId: 'm1',
      props: { text: TEXT, isFirstOfReply: true },
    })

    expect(await ui.find({ type: 'Markdown', text: 'One.' })).toBeDefined()
    expect(await ui.find({ type: 'Markdown', text: 'Which branch?' })).toBeDefined()
    expect(await ui.find({ type: 'Button', text: '1: main ★' })).toBeDefined()
    expect(await ui.find({ type: 'Button', text: '2: dev' })).toBeDefined()
    expect(await ui.find({ type: 'Button', text: 'reply…' })).toBeDefined()
    // Nothing is handed back beneath the hook: a second block would not draw.
    expect(await ui.find({ type: 'Text', text: 'One.' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: 'Which branch?' })).toBeUndefined()
  })

  test('MessageDisplay fenced record folds without losing the report or inventing a reply button', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({ type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }))
    const ui = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId: 'fenced-record',
      props: { text: renderedFenceRecord('~~~', true), isFirstOfReply: true },
    })
    expect(await ui.find({ type: 'Text', text: 'Report.' })).toBeDefined()
    expect(await ui.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await ui.find({ type: 'Button', text: 'reply…' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: '● need input' })).toBeUndefined()
  })

  test('the terminal keeps the engine\'s own drawing of each span body', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? e.component)],
    }))
    const ui = await $.ui.mount({
      plugin: PLUGIN,
      surface: 'terminal',
      component: 'AssistantMessage',
      requestId: 'm1',
      props: { text: TEXT, isFirstOfReply: true },
    })

    expect(await ui.find({ type: 'Text', text: '● message' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'One.' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'Which branch?' })).toBeDefined()
    expect(await ui.find({ type: 'Markdown' })).toBeUndefined()
    expect(await ui.find({ type: 'Button', text: '1: main ★' })).toBeDefined()
  })

  test('without MAWS, the report band and its press still switch the desktop transcript', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? e.component)],
    }))
    const message = await $.ui.mount({
      plugin: PLUGIN, surface: 'desktop', component: 'AssistantMessage',
      requestId: 'm1', props: { text: TEXT, isFirstOfReply: true },
    })
    const band = await $.ui.mount({
      plugin: PLUGIN, surface: 'desktop', component: 'AbovePrompt',
      props: {
        hasSurvey: false, isWorking: false, maxRows: 5, bodyColumns: 80,
        scroll: { offset: 0, bodyRows: 5 }, view: {},
      },
    })
    expect(await message.find({ type: 'Markdown', text: 'Which branch?' })).toBeDefined()
    expect(await band.find({ type: 'Button', text: 'full transcript' })).toBeDefined()
    await band.press({ key: 'to-human-mode' })
    expect(await band.find({ type: 'Button', text: 'report only' })).toBeDefined()
    expect(await message.find({ type: 'Text', text: TEXT })).toBeDefined()
    expect(await message.find({ type: 'Markdown' })).toBeUndefined()
  })

  test('markdownBlocks strips control characters and cuts under the cap at paragraph breaks', async () => {
    expect(markdownBlocks('a\u001b[2mb\u001b[0m\r\nc\td')).toEqual(['ab\nc\td'])

    const paragraph = 'x'.repeat(6000)
    const blocks = markdownBlocks(`${paragraph}\n\n${paragraph}\n\nend`)
    expect(blocks).toEqual([paragraph, `${paragraph}\n\nend`])
    expect(blocks.every((block) => block.length <= 10000)).toBe(true)

    const long = markdownBlocks('y'.repeat(25000))
    expect(long.map((block) => block.length)).toEqual([10000, 10000, 5000])
  })
})

describe('isRead', () => {
  test('questions and agent spawns stay visible while messaging is working record', async () => {
    expect(['AskUserQuestion', 'mcp__doperpowers__AskUserQuestion', 'Agent', 'Workflow'].map(isRead)).toEqual([true, true, true, true])
    expect(['SendMessage', 'Bash', 'Read', 'Monitor', 'TaskOutput'].map(isRead)).toEqual([false, false, false, false, false])
  })
})
