import { describe, expect, test, tier } from 'claude-code/testing'

import type { Question, RowKind } from '../../hooks/mods/to-human'
import { answerOf, answerText, parse, pending, questionHead, runStart } from '../../hooks/mods/to-human'

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
  })

  test('answerText names the question and the choice, and answerOf reads it back', async () => {
    const text = answerText('Which backend?', 'Postgres')

    expect(text).toBe('Answering "Which backend?": Postgres')
    expect(answerOf(text)).toEqual({ head: 'Which backend?', answer: 'Postgres' })
    expect(answerOf('Answering "Which backend?": ')).toEqual({ head: 'Which backend?', answer: '' })
    expect(answerOf(answerText('Which format?', 'Use "fast": mode'))).toEqual({ head: 'Which format?', answer: 'Use "fast": mode' })
    expect(answerOf('Just a prompt.')).toBeUndefined()
    // The engine frames a prompt a plugin submitted; the transcript keeps the frame.
    expect(
      answerOf('The doperpowers plugin sent a message:\nAnswering "Which backend?": Postgres\n\nThis is how Claude Code surfaces a prompt.'),
    ).toEqual({ head: 'Which backend?', answer: 'Postgres' })
  })

  const ask = (id: string, head: string): Question => ({ id, requestId: id, head, choices: [] })

  test('pending is the newest question neither answered nor dismissed', async () => {
    const questions = [ask('q1', 'First?'), ask('q2', 'Second?'), ask('q3', 'Third?')]

    expect(pending(questions, new Map(), new Set())?.id).toBe('q3')
    expect(pending(questions, new Map([['Third?', 'x']]), new Set())?.id).toBe('q2')
    expect(pending(questions, new Map([['Third?', 'x']]), new Set(['Second?']))?.id).toBe('q1')
    expect(pending(questions, new Map([['Third?', 'x'], ['First?', 'y']]), new Set(['Second?']))).toBeUndefined()
  })
})
