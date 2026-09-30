import { describe, expect, mock, test, tier } from 'claude-code/testing'

import type { RowKind, Task } from '../../hooks/mods/to-human'
import {
  answerText,
  answersOf,
  isRead,
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
      'Reading the file.\n<to-human>Done.</to-human>\n<essential>Tests fail.</essential>',
    )

    expect(parsed.spans).toEqual([
      { kind: 'to-human', text: 'Done.', isOpen: false },
      { kind: 'essential', text: 'Tests fail.', isOpen: false },
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
      '<to-human>\nDone.\n\n<essential>\nTests fail.\n</essential>\nMore.\n</to-human>',
    )

    expect(parsed.spans).toEqual([
      { kind: 'to-human', text: 'Done.', isOpen: false },
      { kind: 'essential', text: 'Tests fail.', isOpen: false },
      { kind: 'to-human', text: 'More.', isOpen: false },
    ])
    expect(parsed.hasRecord).toBe(false)
  })

  test('parse does not let an unclosed mark swallow the marks after it', async () => {
    const parsed = parse('<to-human>Done.\n<essential>Tests fail.</essential>\n<need-input>Which')

    expect(parsed.spans).toEqual([
      { kind: 'to-human', text: 'Done.', isOpen: false },
      { kind: 'essential', text: 'Tests fail.', isOpen: false },
      { kind: 'need-input', text: 'Which', isOpen: true },
    ])
  })

  // Captured from a live session: what the transcript holds once
  // to-human-stream.sh has drawn the marks while the message streamed.
  const streamed =
    'Notes: formatting-only request, no tools needed.\n\n\n' +
    '\u001b[1;36mto human\u001b[0m\n\n\nRivers carry water downhill.\n\n\n' +
    '\u001b[1;33messential\u001b[0m\n\n\nNo files were changed.\n\n\n' +
    '\u001b[2mDone \u2014 nothing else pending.\u001b[0m\n'

  test('parse reads the headers the streaming hook drew over the marks', async () => {
    const parsed = parse(streamed)

    expect(parsed.spans).toEqual([
      { kind: 'to-human', text: 'Rivers carry water downhill.', isOpen: false },
      { kind: 'essential', text: 'No files were changed.', isOpen: false },
    ])
    expect(parsed.hasRecord).toBe(true)
  })

  test('parse ends a span at the record that follows it', async () => {
    const parsed = parse(
      '\u001b[1;36mto human\u001b[0m\n\nKept.\n\u001b[2mDropped from the span.\u001b[0m\n',
    )

    expect(parsed.spans).toEqual([{ kind: 'to-human', text: 'Kept.', isOpen: false }])
    expect(parsed.hasRecord).toBe(true)
  })

  test('parse finds no spans in an unmarked message', async () => {
    const parsed = parse('Plain reply.')

    expect(parsed.spans).toEqual([])
    expect(parsed.hasRecord).toBe(true)
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
    const parsed = parse('<to-human>\nPick.\n<choice>A</choice>\n</to-human>')

    expect(parsed.spans).toEqual([{ kind: 'to-human', text: 'Pick.\n<choice>A</choice>', isOpen: false }])
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
  const agents = new Set(['a5d804ff68753fdeb'])
  const isAgents = (task: Task) => task.id !== undefined && agents.has(task.id)

  test('a prompt the person typed, or one of unknown origin, is theirs', async () => {
    expect(promptRow({ origin: { kind: 'composer' } }, isAgents)).toBe('user')
    expect(promptRow({ origin: { kind: 'bridge' } }, isAgents)).toBe('user')
    expect(promptRow({ origin: { kind: 'unclassified' } }, isAgents)).toBe('user')
    expect(promptRow({}, isAgents)).toBe('user')
  })

  test('a delivery of the model\'s own business is working record', async () => {
    expect(promptRow({ origin: { kind: 'scheduled-trigger' } }, isAgents)).toBe('record')
    expect(promptRow({ origin: { kind: 'coordinator' } }, isAgents)).toBe('record')
    // A background command's notification: a task no agent of the session ran.
    expect(promptRow({ origin: { kind: 'task-notification' }, task: { id: 'br5d455do', toolUseId: 'toolu_1' } }, isAgents)).toBe(
      'record',
    )
  })

  test('a message someone else sent, and the finish of an agent, are rows the person reads', async () => {
    expect(promptRow({ origin: { kind: 'peer' }, from: { name: 'reviewer' } }, isAgents)).toBe('marked')
    expect(promptRow({ origin: { kind: 'peer-send-message' }, from: { name: 'lead' } }, isAgents)).toBe('marked')
    expect(promptRow({ origin: { kind: 'task-notification' }, task: { id: 'a5d804ff68753fdeb' } }, isAgents)).toBe('marked')
  })
})

describe('rows', () => {
  // The plugin the runner stages the mods as.
  const PLUGIN = 'doperpowers-mods'

  test('a notification whose agent lookup is pending keeps the place it first drew in', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    // The engine's own drawing beneath the mod: the row's text, one line.
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? e.component)],
    }))
    // The agent list, held until the test lets it go: the rows after the
    // notification draw while its lookup is pending.
    let release: () => void = () => {}
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    on('agent.list', async () => {
      await held
      return { value: [] }
    })

    const message = (requestId: string, text: string) =>
      $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: true } })
    const marked1 = message('m1', '<to-human>One.</to-human>')
    const record1 = message('u1', 'Working.')
    const notification = $.ui.mount({
      plugin: PLUGIN,
      surface: 'terminal',
      component: 'UserMessage',
      requestId: 'n1',
      props: { text: 'Background command "x" completed', origin: { kind: 'task-notification' }, isExpanded: false, task: { id: 'b1' } },
    })
    const marked2 = message('m2', '<to-human>Two.</to-human>')
    const record2 = message('u2', 'More.')
    const [, first, , second] = await Promise.all([marked1, record1, marked2, record2])
    release()
    const note = await notification

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

describe('isRead', () => {
  test('the question dialog and the agent tools draw as the person reads them; the rest is record', async () => {
    expect(['AskUserQuestion', 'Agent', 'SendMessage', 'Workflow'].map(isRead)).toEqual([true, true, true, true])
    expect(['Bash', 'Read', 'Monitor', 'TaskOutput'].map(isRead)).toEqual([false, false, false, false])
  })
})
