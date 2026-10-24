import type { EngineInterface, On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import type { RowKind } from '../../hooks/mods/to-human'
import { MESSAGE_TOOL } from '../../hooks/mods/message'
import { START_WAIT_MS, editorUrl, errorsIn, fileLinks, isRead, markdownBlocks, newView, parse, placeAll, placeArgs, placesIn, promptRow, registerToHuman, reorder, runEnd, runStart, sessionPlaceArgs } from '../../hooks/mods/to-human'

// The kit runs tests with the timer the hooks' declarations leave out.
declare const setTimeout: (callback: (value?: unknown) => void, ms: number) => unknown

tier('user')

/** A `next` as the engine hands a hook the tests call themselves: the chain beneath, and the dispatch's signal. */
const beneath = <F extends (e: Record<string, unknown>) => Promise<unknown>>(chain: F, signal = new AbortController().signal) => Object.assign(chain, { signal })

/** Resolves after `ms` milliseconds of the kit's own timer. */
const tick = (ms = 1) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * The view's hooks called as the engine would call them, over a start-up read
 * whose conversation (a mark sent before) answers once `release` runs, and a
 * clock whose wait for the rows the test ends itself (`endWait`).
 */
function startingView() {
  type Event = Record<string, unknown>
  type Handler = (engine: EngineInterface, e: Event, next: unknown) => Promise<unknown>
  const hooks: { event: string; matcher: Event; handler: Handler }[] = []
  const on = ((event: string, ...rest: unknown[]) => {
    hooks.push({ event, matcher: rest.length > 1 ? (rest[0] as Event) : {}, handler: rest[rest.length - 1] as Handler })
  }) as unknown as On
  registerToHuman(on)
  const state = { reads: 0, invalidations: 0, waits: [] as number[] }
  let release = () => {}
  const gate = new Promise<void>((resolve) => (release = resolve))
  let endWait = () => {}
  const engine = {
    env: { get: async () => undefined },
    session: {
      messages: async () => ((state.reads += 1), await gate, [{ role: 'assistant', text: '<message>Earlier.</message>', toolUses: [] }]),
      id: async () => 's1',
    },
    process: { run: async () => ({ exitCode: 1, stdout: '', stderr: '' }) },
    clock: {
      after: (ms: number, fn: () => void) => (state.waits.push(ms), (endWait = fn), { cancel: () => (endWait = () => {}) }),
      now: async () => 0,
    },
    ui: {
      resolve: () => ({ Box: 'Box', Text: 'Text', Button: 'Button', Markdown: 'Markdown' }),
      invalidate: () => {
        state.invalidations += 1
      },
      log: () => {},
    },
  } as unknown as EngineInterface
  const hook = (event: string, component?: string) => hooks.find((h) => h.event === event && h.matcher.component === component)!.handler
  const draw = (requestId: string, signal = new AbortController().signal) =>
    hook('ui.render', 'AssistantMessage')(
      engine,
      { surface: 'terminal', component: 'AssistantMessage', requestId, props: { text: 'Reading.', isFirstOfReply: true } },
      beneath(async () => ({ type: 'Text', children: ['raw'] }), signal),
    )
  const start = () => hook('session.start')(engine, { cwd: '/w', surface: 'terminal', isInteractive: true }, beneath(async () => ({ cwd: '/w' })))
  return { state, draw, start, release: () => release(), endWait: () => endWait() }
}

describe('register', () => {
  test('parse splits marked spans from the working record', async () => {
    const parsed = parse(
      'Reading the file.\n<message>Done.</message>\n<insight>Tests fail.</insight>',
    )

    expect(parsed.spans).toEqual([
      { kind: 'message', text: 'Done.', isOpen: false },
      { kind: 'message', text: 'Tests fail.', isOpen: false },
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
    const parsed = parse('<message>Which branch')

    expect(parsed.spans).toEqual([{ kind: 'message', text: 'Which branch', isOpen: true }])
    expect(parsed.hasRecord).toBe(false)
  })

  test('parse reads old need-input marks as messages, their choice lines as text', async () => {
    const question = 'Which backend?\n<choice recommended>Postgres: already running</choice>\n<choice>SQLite</choice>'
    expect(parse(`<need-input>\n${question}\n</need-input>\nWorking.`)).toEqual({
      spans: [{ kind: 'message', text: question, isOpen: false }],
      hasRecord: true,
    })
    expect(parse('<need-input>Which branch').spans).toEqual([{ kind: 'message', text: 'Which branch', isOpen: true }])
  })

  test('parse lifts a mark nested inside another into a span of its own', async () => {
    const parsed = parse(
      '<message>\nDone.\n\n<insight>\nTests fail.\n</insight>\nMore.\n</message>',
    )

    expect(parsed.spans).toEqual([
      { kind: 'message', text: 'Done.', isOpen: false },
      { kind: 'message', text: 'Tests fail.', isOpen: false },
      { kind: 'message', text: 'More.', isOpen: false },
    ])
    expect(parsed.hasRecord).toBe(false)
  })

  test('parse does not let an unclosed mark swallow the marks after it', async () => {
    const parsed = parse('<message>Done.\n<insight>Tests fail.</insight>\n<need-input>Which')

    expect(parsed.spans).toEqual([
      { kind: 'message', text: 'Done.', isOpen: false },
      { kind: 'message', text: 'Tests fail.', isOpen: false },
      { kind: 'message', text: 'Which', isOpen: true },
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

  test('parse reads an old insight as a message, in either form', async () => {
    expect(parse('Editing.\n<insight>The cache key is the path.</insight>').spans).toEqual([
      { kind: 'message', text: 'The cache key is the path.', isOpen: false },
    ])
    expect(parse('\u001b[1;33minsight\u001b[0m\n\nThe cache key is the path.\n').spans).toEqual([
      { kind: 'message', text: 'The cache key is the path.', isOpen: false },
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

  test('quoted closers do not end a mark', async () => {
    const question = 'Which form?\nWrite `<choice>A</choice>` lines.\n```\n</need-input>\n<choice>B</choice>\n```'
    expect(parse(`<need-input>${question}\n<choice recommended>Yes</choice>\n</need-input>`)).toEqual({
      spans: [{ kind: 'message', text: `${question}\n<choice recommended>Yes</choice>`, isOpen: false }],
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
          { kind: 'message', text: 'Go?', isOpen: false }], hasRecord: false,
      })
    }
    expect(parse('<message>```bash\nnpm test\n```\n</message>\n<need-input>Go?</need-input>').spans).toEqual([
      { kind: 'message', text: '```bash\nnpm test\n```', isOpen: false }, { kind: 'message', text: 'Go?', isOpen: false },
    ])
    const example = 'Example syntax:\n```text\n```</message>\n<need-input>Example only?</need-input>\n```\nEnd of example.'
    expect(parse(`<message>${example}</message>`)).toEqual({
      spans: [{ kind: 'message', text: example, isOpen: false }], hasRecord: false,
    })
  })

  test('rendered orange messages keep quoted tags; an old need-input header reads as a message with its markers as text', async () => {
    expect(parse(`\u001b[1;38;2;215;119;87mmessage\u001b[0m\n\n${sentence}\n`)).toEqual({
      spans: [{ kind: 'message', text: sentence, isOpen: false }], hasRecord: false,
    })
    expect(parse('\u001b[1;35mneed input\u001b[0m\n\nExample:\n```\n◇ literal\n```\n◆ Yes\n').spans).toEqual([
      { kind: 'message', text: 'Example:\n```\n◇ literal\n```\n◆ Yes', isOpen: false },
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

describe('transcript order', () => {
  // The plugin under test.
  const PLUGIN = 'to-human'

  test('the search lists each row by its id and each call by its tool_use_id, in the file\'s order', async () => {
    expect(placeArgs('/t.jsonl').includes('/t.jsonl')).toBe(true)
    const stdout = ['"uuid":"u1"', '"type":"tool_use","id":"toolu_1"', '"uuid":"u2"', '"isApiErrorMessage":true', '', 'noise'].join('\n')

    expect(placesIn(stdout)).toEqual(['u1', 'toolu_1', 'u2'])
  })

  test('the search names an API error by the row whose line flags it', async () => {
    const stdout = ['"isApiErrorMessage":true', '"uuid":"u1"', '"type":"tool_use","id":"toolu_1"', '"uuid":"e1"', '"isApiErrorMessage":true', '"uuid":"u2"'].join('\n')

    expect(errorsIn(stdout)).toEqual(['e1'])
  })

  test('drawn rows sort by their places; a row with none keeps its spot after them', async () => {
    const view = newView(() => true)
    view.order.push('c', 'unplaced', 'b', 'a')
    placeAll(view, ['a', 'b', 'c'])
    placeAll(view, ['a'], 99)

    expect(reorder(view)).toBe(true)
    expect(view.order).toEqual(['a', 'b', 'c', 'unplaced'])
    expect(reorder(view)).toBe(false)
  })

  test("the hooks beneath a resumed session's start run while its transcript is searched", async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    let release = () => {}
    const searched = new Promise<void>((resolve) => (release = resolve))
    on('process.run', async () => {
      await searched
      return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    let isReached = false
    on('classic.SessionStart', () => ((isReached = true), {}))
    const started = $.classic.SessionStart({ source: 'resume', transcript_path: '/t.jsonl' })
    for (let i = 0; i < 100 && !isReached; i++) {
      await new Promise((resolve) => setTimeout(resolve, 1))
    }
    expect(isReached).toBe(true)
    release()
    await started
  })

  test('a resumed transcript drawn newest first opens each run at its first row', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({ type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }))
    const transcript = ['m1', 'r1', 'r2', 'm2', 'r3'].map((id) => `"uuid":"${id}"`).join('\n')
    on('process.run', async () => ({ value: { exitCode: 0, stdout: transcript, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
    on('classic.SessionStart', () => ({}))
    await $.classic.SessionStart({ source: 'resume', transcript_path: '/t.jsonl' })
    const message = (requestId: string, text: string) =>
      $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: false } })

    // The fullscreen transcript lays out the newest rows first, then the
    // older ones as the human scrolls up.
    const r3 = await message('r3', 'Pushing.')
    await message('m2', '<message>Two.</message>')
    const r2 = await message('r2', 'Testing.')
    const r1 = await message('r1', 'Reading.')
    await message('m1', '<message>One.</message>')

    expect(await r1.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await r2.find({ type: 'Button' })).toBeUndefined()
    expect(await r3.find({ type: 'Button', text: 'working record' })).toBeDefined()

    // Unfolded from its first row, the run ends at its last.
    await r1.press({ key: 'to-human-toggle' })
    expect(await r2.find({ type: 'Button', text: 'fold to report' })).toBeDefined()
    expect(await r1.find({ type: 'Button', text: 'fold to report' })).toBeUndefined()
  })

  // On a --resume start the engine draws the history before the module
  // loads, then asks it about every row; its first answer must already fold
  // (board #105: what stays raw is the terminal's scrollback, which
  // live-resume-check.py pins).
  test("a resumed history's marked row folds from the module's first answer", async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    // A folded marked row never draws the engine's own: any next(e) for it
    // means an answer, the first included, came out raw (the kit redraws a
    // mount the view invalidates before a find reads it).
    let rawAnswers = 0
    on('ui.render', (_, e) => {
      if (e.component === 'AssistantMessage') rawAnswers += 1
      return { type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }
    })
    const row = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId: 'm1',
      props: { text: '<message>Done.</message>', isFirstOfReply: true },
    })
    const texts = (await row.findAll({ type: 'Text' })).map((text) => text.text)
    expect(texts.some((text) => text.includes('<message>'))).toBe(false)
    expect(texts.some((text) => text.includes('● message'))).toBe(true)
    expect(rawAnswers).toBe(0)
  })

  test('rows drawn before the transcript is read move to their places once it is', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({ type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }))
    const transcript = ['m1', 'r1', 'r2', 'm2'].map((id) => `"uuid":"${id}"`).join('\n')
    on('process.run', async () => ({ value: { exitCode: 0, stdout: transcript, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
    on('classic.SessionStart', () => ({}))
    const message = (requestId: string, text: string) =>
      $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: false } })
    await message('m2', '<message>Two.</message>')
    const r2 = await message('r2', 'Testing.')
    const r1 = await message('r1', 'Reading.')
    await message('m1', '<message>One.</message>')

    await $.classic.SessionStart({ source: 'resume', transcript_path: '/t.jsonl' })

    expect(await r1.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await r2.find({ type: 'Button' })).toBeUndefined()
  })
})

// The fullscreen transcript holds a row off its window at the height it last
// had and lets go of it as the row scrolls back in at the window's top edge,
// where the release reads as the transcript pulling the person back down. So
// the view does not fold a row it drew with height while that row may be off
// the window: not after its module starts over, and not after a fold the
// person asked for, whose run's first row it brings into view.
describe('rows off the window', () => {
  const PLUGIN = 'to-human'

  test("a module that starts over in a session that has sent a mark folds from its first answer, its rows in the transcript's order", async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    // Any next(e) for a row is an answer that came out as the engine draws it.
    let rawAnswers = 0
    on('ui.render', (_, e) => {
      if (e.component !== 'AbovePrompt') rawAnswers += 1
      return { type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }
    })
    on('session.messages', () => ({ value: [{ role: 'assistant', text: '<message>Earlier.</message>', toolUses: [] }] }))
    on('session.id', () => ({ value: 's1' }))
    const searches: (readonly string[])[] = []
    const transcript = ['m1', 'r1', 'r2', 'm2'].map((id) => `"uuid":"${id}"`).join('\n')
    on('process.run', async (_, e) => {
      searches.push(e.argv)
      return { value: { exitCode: 0, stdout: transcript, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    const message = (requestId: string, text: string) =>
      $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: false } })

    // No session start: the rows are asked about as they stand, newest first.
    const r2 = await message('r2', 'Testing.')
    const r1 = await message('r1', 'Reading.')

    expect(rawAnswers).toBe(0)
    expect(await r1.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await r2.find({ type: 'Button' })).toBeUndefined()
    expect(searches).toEqual([sessionPlaceArgs('s1')])
  })

  // The kit's mounted rows do not say where the transcript scrolls, so the
  // hooks are called as the engine would call them.
  test("a fold brings the run's first row into view only when its top is out of the window, by the requestId it draws under", async () => {
    type Event = Record<string, unknown>
    type Handler = (engine: EngineInterface, e: Event, next: (e: Event) => Promise<unknown>) => unknown
    const hooks: { event: string; matcher: Event; handler: Handler }[] = []
    const on = ((event: string, ...rest: unknown[]) => {
      hooks.push({ event, matcher: rest.length > 1 ? rest[0] as Event : {}, handler: rest[rest.length - 1] as Handler })
    }) as unknown as On
    registerToHuman(on)
    const scrolls: unknown[] = []
    const engine = {
      env: { get: async () => undefined },
      session: { messages: async () => [], id: async () => 's1' },
      process: { run: async () => ({ exitCode: 1, stdout: '', stderr: '' }) },
      clock: { after: () => ({ cancel: () => {} }), now: async () => 0 },
      ui: {
        resolve: () => ({ Box: 'Box', Text: 'Text', Button: 'Button', Markdown: 'Markdown' }),
        invalidate: () => {},
        log: () => {},
        scroll: async (args: unknown) => (scrolls.push(args), {}),
      },
    } as unknown as EngineInterface
    const render = (component: string) => hooks.find((h) => h.event === 'ui.render' && h.matcher.component === component)!
    const toggle = hooks.find((h) => h.event === 'ui.press' && h.matcher.element === 'to-human-toggle')!
    const draw = (component: string, requestId: string, props: Event) =>
      render(component).handler(engine, { surface: 'terminal', component, requestId, props }, beneath(async () => ({ type: 'Text', children: [component] })))
    // The closure of the button labelled `label` in a drawn tree.
    const pressOf = (node: unknown, label: string): (() => void) | undefined => {
      if (typeof node !== 'object' || node === null) return undefined
      const element = node as { props?: { label?: string }; onPress?: () => void }
      if (element.props?.label === label && typeof element.onPress === 'function') return element.onPress
      return Object.values(node).map((child) => pressOf(child, label)).find((press) => press !== undefined)
    }
    // A press as the engine makes it: the hooks, then the button's own closure beneath them.
    const press = (tree: unknown, label: string, surface = 'terminal') =>
      toggle.handler(engine, { surface, element: 'to-human-toggle' }, beneath(async () => (pressOf(tree, label)!(), { element: 'to-human-toggle' })))

    await draw('AssistantMessage', 'm1', { text: '<message>One.</message>', isFirstOfReply: true })
    const calls = [{ tool_use_id: 't1', tool: 'Read', input: {} }]
    // The run's first row, a group, as the window last showed it.
    const start = (onScreen?: unknown) => draw('ToolGroup', 'collapsed-1', { calls, isExpanded: false, ...(onScreen !== undefined && { onScreen }) })
    const end = () => draw('AssistantMessage', 'r2', { text: 'Reading.', isFirstOfReply: false })
    await start()
    await end()
    await draw('AssistantMessage', 'm2', { text: '<message>Two.</message>', isFirstOfReply: true })
    // Unfolded from the group, the run read down to its end, the group shown
    // as given, then folded at the end.
    const unfoldAndFold = async (shown: unknown, surface = 'terminal') => {
      await press(await start(), 'working record', surface)
      await start(shown)
      await press(await end(), 'fold to report', surface)
    }

    // Unfolding moves nothing, nor does folding a run whose first row stands
    // whole in the window, or at least its top does: a reveal would stop the
    // transcript following its bottom. Nor where no window says (the main
    // screen holds no row).
    await press(await start(), 'working record')
    await press(await end(), 'fold to report')
    expect(scrolls).toEqual([])
    await unfoldAndFold({ first: 0, last: 3, of: 4 })
    await unfoldAndFold({ first: 0, last: 1, of: 4 })
    expect(scrolls).toEqual([])

    // Out of the window, or its top cut off, the group is brought into view
    // by the id its row draws under.
    await unfoldAndFold(null)
    expect(scrolls).toEqual([{ to: { requestId: 'collapsed-1' }, block: 'nearest' }])
    await unfoldAndFold({ first: 2, last: 3, of: 4 })
    expect(scrolls.length).toBe(2)

    // Another surface keeps where it is: the hold is the fullscreen terminal's.
    await unfoldAndFold(null, 'desktop')
    expect(scrolls.length).toBe(2)
  })

  test('a start-up read cut short by its dispatch is made again by the hooks still waiting, and the row cut short answers at once', async () => {
    const view = startingView()

    // The first row's dispatch starts the read and is superseded while it runs.
    const first = new AbortController()
    const superseded = view.draw('r1', first.signal)
    for (let i = 0; i < 100 && view.state.reads === 0; i++) await tick()
    const waiting = view.draw('r2')
    await tick(5)
    first.abort()
    expect(await Promise.race([superseded.then(() => 'answered'), tick(50).then(() => 'still waiting')])).toBe('answered')
    view.release()

    expect(JSON.stringify(await waiting)).not.toContain('raw')
    expect(view.state.reads).toBe(2)
  })

  test("the start-up read begun at the module's session.start is not cut short by a row's redraw", async () => {
    const view = startingView()
    void view.start()
    const row = new AbortController()
    const superseded = view.draw('r1', row.signal)
    await tick(5)
    row.abort()
    await superseded
    view.release()

    expect(JSON.stringify(await view.draw('r1'))).not.toContain('raw')
    expect(view.state.reads).toBe(1)
  })

  test('the rows wait for the start-up read START_WAIT_MS at most, then draw with what is known, and are asked for again once it lands', async () => {
    const view = startingView()
    void view.start()
    const row = view.draw('r1')
    await tick(5)
    expect(view.state.waits).toEqual([START_WAIT_MS])

    // Past the wait a row draws as the engine does, no mark being known yet,
    // and a row asked about later does not wait at all.
    view.endWait()
    expect(JSON.stringify(await row)).toContain('raw')
    expect(JSON.stringify(await view.draw('r2'))).toContain('raw')

    const asked = view.state.invalidations
    view.release()
    for (let i = 0; i < 100 && view.state.invalidations === asked; i++) await tick()
    expect(view.state.invalidations).toBeGreaterThan(asked)
    expect(JSON.stringify(await view.draw('r1'))).not.toContain('raw')
  })

  test('a session that has sent no mark still draws as the engine does, and no transcript yet places nothing', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({ type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }))
    on('session.messages', () => ({ value: [{ role: 'assistant', text: '`<message>` marks a message.', toolUses: [] }] }))
    on('session.id', () => ({ value: 's1' }))
    on('process.run', async () => ({ value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
    const row = await $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId: 'r1', props: { text: 'Reading.', isFirstOfReply: true } })

    expect(await row.find({ type: 'Text', text: 'Reading.' })).toBeDefined()
    expect(await row.find({ type: 'Button' })).toBeUndefined()
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

  test('the failure of an agent the report shows the spawn of stays in the report', async () => {
    const spawns = new Set(['toolu_agent'])
    const failed = (toolUseId: string) => ({ origin: { kind: 'task-notification' as const }, task: { id: 'a1', toolUseId, status: 'failed' } })
    expect(promptRow(failed('toolu_agent'), spawns)).toBe('marked')
    // A background command that failed is the model's business.
    expect(promptRow(failed('toolu_bash'), spawns)).toBe('record')
    expect(promptRow({ origin: { kind: 'task-notification' }, task: { id: 'a1', toolUseId: 'toolu_agent', status: 'completed' } }, spawns)).toBe('record')
    expect(promptRow({ origin: { kind: 'task-notification' }, task: { id: 'a1', toolUseId: 'toolu_agent', status: 'killed' } }, spawns)).toBe('record')
  })

  test('received agent messages are working record, even without an origin', async () => {
    expect(promptRow({ origin: { kind: 'peer' }, from: { name: 'reviewer' } })).toBe('record')
    expect(promptRow({ origin: { kind: 'peer-send-message' }, from: { name: 'lead' } })).toBe('record')
    expect(promptRow({ from: { name: 'reviewer' } })).toBe('record')
  })

  test('the person\'s answer to an async question stays theirs, with or without the engine\'s framing', async () => {
    const answer = 'The human responded to your async AskUserQuestion (call toolu_01): User has answered your questions: "Which?"="A". Notes: prefer B'
    expect(promptRow({ origin: { kind: 'plugin' }, text: answer })).toBe('user')
    expect(promptRow({ origin: { kind: 'plugin' }, text: `The doperpowers plugin sent a message:\n${answer}` })).toBe('user')
    // The ask moves to the sminos plugin; a transcript holds its framing or doperpowers'.
    expect(promptRow({ origin: { kind: 'plugin' }, text: `The sminos plugin sent a message:\n${answer}` })).toBe('user')
    expect(promptRow({ origin: { kind: 'plugin' }, text: `The cua plugin sent a message:\n${answer}` })).toBe('record')
    // Any other plugin prompt is the model's business.
    expect(promptRow({ origin: { kind: 'plugin' }, text: 'Continue from the summary.' })).toBe('record')
    expect(promptRow({ origin: { kind: 'plugin' }, text: 'The doperpowers plugin sent a message:\nContinue from the summary.' })).toBe('record')
  })

  test('a sminos delivery is read by its frame: the person\'s stays, another session\'s is working record', async () => {
    // The bridge submits both as the person's words, under its own plugin's origin.
    expect(promptRow({ origin: { kind: 'plugin' }, text: '[sminos message from CI-opt id=2808a58d]\nCI-opt: the hold is granted.' })).toBe('record')
    expect(promptRow({ origin: { kind: 'plugin' }, text: '[sminos message from human id=86388163]\nstatus?' })).toBe('user')
    // A `say` arrives in the chat frame; the project's name may hold spaces.
    expect(promptRow({ origin: { kind: 'plugin' }, text: '[sminos chat my project 86388163:7 from human → @you]\n@rover status?' })).toBe('user')
    expect(promptRow({ origin: { kind: 'plugin' }, text: '[sminos chat doperpowers 2808a58d:12 from CI-opt → @you]\nthe hold is granted.' })).toBe('record')
    expect(promptRow({ origin: { kind: 'plugin' }, text: '[sminos chat doperpowers 2808a58d:12 from CI-opt → @you | unread 3]\nthe hold is granted.' })).toBe('record')
    expect(promptRow({ origin: { kind: 'plugin' }, text: '[sminos chat doperpowers 2808a58d:13 from CI-opt → @all]\nheads up' })).toBe('record')
    expect(promptRow({ origin: { kind: 'plugin' }, text: '[sminos chat doperpowers 86388163:8 from human → @all | unread 2]\nstop' })).toBe('user')
    // Typed at the prompt, a chat frame is still the person's.
    expect(promptRow({ origin: { kind: 'composer' }, text: '[sminos chat doperpowers 2808a58d:12 from CI-opt → @you]\nquoted' })).toBe('user')
    // The inbox frame, where no bridge runs, comes with no stamp the engine can name.
    expect(promptRow({ origin: { kind: 'unclassified' }, text: '[sminos message from CI-opt id=2808a58d]\nhi' })).toBe('record')
    // What the person typed is theirs, whatever it opens with.
    expect(promptRow({ origin: { kind: 'composer' }, text: '[sminos message from CI-opt id=2808a58d]\nquoted' })).toBe('user')
    // A plugin's other prompts stay working record.
    expect(promptRow({ origin: { kind: 'plugin' }, text: 'Continue from the summary.' })).toBe('record')
  })
})

describe('rows', () => {
  // The plugin under test.
  const PLUGIN = 'to-human'

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

  test('another session\'s sminos message folds into the run; the person\'s own stays', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? e.component)],
    }))
    const message = (requestId: string, text: string) =>
      $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: true } })
    const delivery = (requestId: string, text: string) =>
      $.ui.mount({
        plugin: PLUGIN,
        surface: 'terminal',
        component: 'UserMessage',
        requestId,
        props: { text, origin: { kind: 'plugin', name: 'doperpowers', asUser: true }, isExpanded: false },
      })
    await message('m1', '<message>Waiting on CI.</message>')
    const peer = await delivery('d1', '[sminos message from CI-opt id=2808a58d]\nCI-opt: the hold is granted.')
    const own = await delivery('d2', '[sminos message from human id=86388163]\nstatus?')

    expect(await peer.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await peer.find({ type: 'Text', text: '[sminos message from CI-opt id=2808a58d]\nCI-opt: the hold is granted.' })).toBeUndefined()
    expect(await own.find({ type: 'Text', text: '[sminos message from human id=86388163]\nstatus?' })).toBeDefined()
  })

  test('the band draws its line under what the hooks beneath draw there', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    // Beneath the view: the ask's open-question line, as the doperpowers plugin draws it.
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [e.component === 'AbovePrompt' ? '1 open question' : String((e.props as { text?: string }).text ?? e.component)],
    }))
    await $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId: 'm1', props: { text: '<message>Asked.</message>', isFirstOfReply: true } })
    const band = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'AbovePrompt',
      props: { hasSurvey: false, isWorking: false, maxRows: 5, bodyColumns: 80, scroll: { offset: 0, bodyRows: 5 }, view: {} },
    })
    const texts = (await band.findAll({ type: 'Text' })).map((text) => text.text)
    expect(texts[0]).toBe('1 open question')
    expect(texts.some((text) => text.includes('to-human view'))).toBe(true)
    expect(await band.find({ type: 'Button', text: 'full transcript' })).toBeDefined()
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

describe('failures', () => {
  const PLUGIN = 'to-human'
  const engineDrawing = (on: On) =>
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? e.component)],
    }))

  const response = (uuid: string, text: string, model = '<synthetic>', agentId?: string) => ({
    message: { type: 'assistant' as const, role: 'assistant' as const, content: [{ type: 'text' as const, text }] },
    door: 'response' as const,
    origin: { kind: 'model' as const, model },
    uuid,
    ...(agentId !== undefined && { agentId }),
  })
  const message = ($: Engine, requestId: string, text: string) =>
    $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: true } })
  const bash = ($: Engine, id: string) =>
    $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'ToolUse', requestId: id,
      props: { tool_use_id: id, tool: 'Bash', input: { command: 'ls' }, isRunning: false, isErrored: false, isInterrupted: false, output: 'ok' },
    } as never)

  test('an API error stays in the report, whether it drew before its row was kept or after', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    const error = 'API Error: Connection refused'
    await message($, 'm1', '<message>Starting.</message>')
    const record = await message($, 'r1', 'Working.')
    const early = await message($, 'e1', error)
    // Drawn before it is kept, it is one more unmarked row of the run.
    expect(await early.find({ type: 'Text', text: error })).toBeUndefined()

    await $.session.append(response('e1', error))
    await $.session.append(response('e2', 'API Error: 400 bad request'))
    const late = await message($, 'e2', 'API Error: 400 bad request')

    expect(await early.find({ type: 'Text', text: error })).toBeDefined()
    expect(await late.find({ type: 'Text', text: 'API Error: 400 bad request' })).toBeDefined()
    expect(await record.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await record.find({ type: 'Text', text: 'Working.' })).toBeUndefined()
  })

  test('the turn going on after an API error opens a run of its own', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    const error = 'API Error: Connection lost mid-response. The response above may be incomplete.'
    await message($, 'm1', '<message>Starting.</message>')
    await $.session.append(response('e1', error))
    const row = await message($, 'e1', error)
    const after = await bash($, 'toolu_b1')

    expect(await row.find({ type: 'Text', text: error })).toBeDefined()
    expect(await row.find({ type: 'Button' })).toBeUndefined()
    expect(await after.find({ type: 'Button', text: 'working record' })).toBeDefined()
  })

  test("the model's text, a subagent's error and the stand-in for no response are working record", async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    await message($, 'm1', '<message>Starting.</message>')
    await $.session.append(response('r1', 'API Error: quoted by the model', 'claude-opus-5-5'))
    await $.session.append(response('r2', 'API Error: terminated', '<synthetic>', 'a1'))
    await $.session.append(response('r3', 'No response requested.'))
    const rows = [
      await message($, 'r1', 'API Error: quoted by the model'),
      await message($, 'r2', 'API Error: terminated'),
      await message($, 'r3', 'No response requested.'),
    ]

    // One run, folded behind the first row's button.
    expect(await rows[0]!.find({ type: 'Button', text: 'working record' })).toBeDefined()
    for (const row of rows) {
      expect((await row.findAll({ type: 'Text' })).some((text) => text.text.startsWith('API Error') || text.text.startsWith('No response'))).toBe(false)
    }
  })

  test('an API error a resumed transcript holds stays in the report', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    const transcript = ['"uuid":"m1"', '"uuid":"r1"', '"uuid":"e1"', '"isApiErrorMessage":true', '"uuid":"p2"'].join('\n')
    on('process.run', async () => ({ value: { exitCode: 0, stdout: transcript, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
    on('classic.SessionStart', () => ({}))
    await $.classic.SessionStart({ source: 'resume', transcript_path: '/t.jsonl' })
    await message($, 'm1', '<message>Starting.</message>')
    const record = await message($, 'r1', 'Working.')
    const row = await message($, 'e1', 'API Error: Connection refused')

    expect(await row.find({ type: 'Text', text: 'API Error: Connection refused' })).toBeDefined()
    expect(await record.find({ type: 'Button', text: 'working record' })).toBeDefined()
  })

  test('a spawned agent\'s failure notification stays in the report, a failed command\'s does not', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    await $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId: 'm1', props: { text: '<message>Dispatching.</message>', isFirstOfReply: true } })
    await $.ui.mount({
      plugin: PLUGIN,
      surface: 'terminal',
      component: 'ToolUse',
      requestId: 'toolu_agent',
      props: { tool_use_id: 'toolu_agent', tool: 'Agent', input: {}, isInterrupted: false },
    } as never)
    const notification = (requestId: string, text: string, toolUseId: string) =>
      $.ui.mount({
        plugin: PLUGIN,
        surface: 'terminal',
        component: 'UserMessage',
        requestId,
        props: { text, origin: { kind: 'task-notification' }, isExpanded: false, task: { id: requestId, toolUseId, status: 'failed' } },
      })
    const agent = await notification('n1', 'Agent "Review" failed: Agent terminated early due to an API error: terminated', 'toolu_agent')
    const shell = await notification('n2', 'Background command "npm test" failed with exit code 1', 'toolu_bash')

    expect(await agent.find({ type: 'Text', text: 'Agent "Review" failed: Agent terminated early due to an API error: terminated' })).toBeDefined()
    expect(await shell.find({ type: 'Text', text: 'Background command "npm test" failed with exit code 1' })).toBeUndefined()
  })
})

describe('mixed', () => {
  const PLUGIN = 'to-human'

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
  const PLUGIN = 'to-human'
  // An old transcript's question: its mark reads as a message, its choice lines as text.
  const QUESTION = 'Which branch?\n<choice recommended>main</choice>\n<choice>dev</choice>'
  const TEXT = `<message>One.</message>\n<need-input>${QUESTION}\n</need-input>`

  test('a remote surface draws every span body as its own Markdown, an old question included', async ($, on) => {
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
    expect(await ui.find({ type: 'Markdown', text: QUESTION })).toBeDefined()
    expect(await ui.find({ type: 'Button' })).toBeUndefined()
    // Nothing is handed back beneath the hook: a second block would not draw.
    expect(await ui.find({ type: 'Text', text: 'One.' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: QUESTION })).toBeUndefined()
  })

  test('MessageDisplay fenced record folds without losing the report or inventing a reply button', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({ type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }))
    const ui = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId: 'fenced-record',
      props: { text: renderedFenceRecord('~~~', true), isFirstOfReply: true },
    })
    expect(await ui.find({ type: 'Markdown', text: 'Report.' })).toBeDefined()
    expect(await ui.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await ui.find({ type: 'Button', text: 'reply…' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: '● need input' })).toBeUndefined()
  })

  test('the terminal draws each span body as its own Markdown, directly under its label', async ($, on) => {
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
    expect(await ui.find({ type: 'Text', text: '  message' })).toBeDefined()
    expect(await ui.find({ type: 'Markdown', text: 'One.' })).toBeDefined()
    expect(await ui.find({ type: 'Markdown', text: QUESTION })).toBeDefined()
    // The engine's block is not handed back: it would carry its row margin,
    // a blank line between the label and the body.
    expect(await ui.find({ type: 'Text', text: 'One.' })).toBeUndefined()
    expect(await ui.find({ type: 'Button' })).toBeUndefined()
  })

  test('on the terminal a plain click on a span\'s file link opens VS Code at its line', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({ type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }))
    const runs: string[][] = []
    on('process.run', async (_, e) => {
      runs.push([...e.argv])
      return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    const text = '<message>Read [the plan](/repo/plan.md#L12).</message>'
    const terminal = await $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId: 'm1', props: { text, isFirstOfReply: true } })

    expect(await terminal.find({ type: 'Markdown', text: 'Read [\uea7b the plan](file:///repo/plan.md#L12).' })).toBeDefined()
    await terminal.press({ key: 'to-human-links:0:0', link: { href: 'file:///repo/plan.md#L12' } })
    expect(runs).toContainEqual(['open', 'vscode://file/repo/plan.md:12'])

    // A remote surface opens nothing on this machine: the link stays as written.
    const desktop = await $.ui.mount({ plugin: PLUGIN, surface: 'desktop', component: 'AssistantMessage', requestId: 'm2', props: { text, isFirstOfReply: true } })
    expect(await desktop.find({ type: 'Markdown', text: 'Read [the plan](/repo/plan.md#L12).' })).toBeDefined()
  })

  test('the report\'s rows stand a line apart, as the engine\'s rows do', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? e.component)],
    }))
    const message = (requestId: string, text: string) =>
      $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: true } })
    const marked = await message('m1', '<message>One.</message>')
    const record = await message('r1', 'Working.')
    const mixed = await message('m2', '<message>Two.</message>\nNotes.')
    const band = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'AbovePrompt',
      props: { hasSurvey: false, isWorking: false, maxRows: 5, bodyColumns: 80, scroll: { offset: 0, bodyRows: 5 }, view: {} },
    })
    const marginTop = async (ui: { drawn: () => Promise<unknown> }) => ((await ui.drawn()) as { props?: { marginTop?: number } }).props?.marginTop
    expect(await marginTop(marked)).toBe(1)
    expect(await marginTop(record)).toBe(1)
    expect((await band.findAll({ type: 'Box' })).some((box) => box.props.marginTop === 1 && box.text.includes('full transcript'))).toBe(true)
    // A mixed message's button stands a line below its body.
    expect((await mixed.findAll({ type: 'Box' })).some((box) => box.props.marginTop === 1 && box.text === '› working record')).toBe(true)
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
    expect(await message.find({ type: 'Markdown', text: QUESTION })).toBeDefined()
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

describe('file links', () => {
  test('fileLinks draws local file links as file URLs behind an icon, and leaves web links and code alone', async () => {
    const { text, targets } = fileLinks('See [plan](/repo/plan.md#L12), [노트](/repo/노트.md), [site](https://x.dev), `[raw](/repo/a.md)`.')

    expect(targets).toEqual(['file:///repo/plan.md#L12', 'file:///repo/%EB%85%B8%ED%8A%B8.md'])
    expect(text).toBe('See [\uea7b plan](file:///repo/plan.md#L12), [\uea7b 노트](file:///repo/%EB%85%B8%ED%8A%B8.md), [site](https://x.dev), `[raw](/repo/a.md)`.')
    expect(fileLinks('```\n[raw](/repo/a.md)\n```').targets).toEqual([])
  })

  test('fileLinks takes a path with parentheses whole', async () => {
    const { text, targets } = fileLinks('Open [page](/repo/app/(auth)/page.tsx#L42).')

    expect(targets).toEqual(['file:///repo/app/(auth)/page.tsx#L42'])
    expect(text).toBe('Open [\uea7b page](file:///repo/app/(auth)/page.tsx#L42).')
  })

  test('fileLinks leaves a link whose href the engine would refuse as written', async () => {
    const long = `[long](/repo/${'노'.repeat(300)}.md) and [short](/repo/a.md)`
    const { text, targets } = fileLinks(long)

    expect(targets).toEqual(['file:///repo/a.md'])
    expect(text).toBe(`[long](/repo/${'노'.repeat(300)}.md) and [\uea7b short](file:///repo/a.md)`)
  })

  test('fileLinks leaves a link reaching into code, and an escaped opener, as written', async () => {
    const reaching = 'Write [For example, `[raw](/repo/a.md)`] and \\[raw](/repo/b.md), then [real](/repo/c.md).'
    const { text, targets } = fileLinks(reaching)

    expect(targets).toEqual(['file:///repo/c.md'])
    expect(text).toBe('Write [For example, `[raw](/repo/a.md)`] and \\[raw](/repo/b.md), then [\uea7b real](file:///repo/c.md).')
  })

  test('editorUrl opens the file at the line its target names', async () => {
    expect(editorUrl('file:///repo/plan.md#L12')).toBe('vscode://file/repo/plan.md:12')
    expect(editorUrl('file:///repo/plan.md#L3-L9')).toBe('vscode://file/repo/plan.md:3')
    expect(editorUrl('/repo/plan.md')).toBe('vscode://file/repo/plan.md')
    expect(editorUrl('https://x.dev/plan.md')).toBeUndefined()
  })
})

describe('isRead', () => {
  test('questions, agent spawns and the message tool stay visible while other messaging is working record', async () => {
    expect(['AskUserQuestion', 'mcp__doperpowers__AskUserQuestion', 'mcp__sminos__AskUserQuestion', 'Agent', 'Workflow', MESSAGE_TOOL].map(isRead)).toEqual([true, true, true, true, true, true])
    expect(['SendMessage', 'Bash', 'Read', 'Monitor', 'TaskOutput'].map(isRead)).toEqual([false, false, false, false, false])
  })
})

describe('the message tool', () => {
  const PLUGIN = 'to-human'
  const engineDrawing = (on: On) =>
    on('ui.render', (_, e) => ({
      type: 'Text',
      children: [String((e.props as { text?: string }).text ?? (e.component === 'ToolResult' ? 'sent' : e.component))],
    }))
  type Call = { input: unknown; isRunning?: boolean; isErrored?: boolean; isInterrupted?: boolean; output?: unknown }
  const callRow = ($: Engine, id: string, { input, isRunning = false, isErrored = false, isInterrupted = false, output }: Call) =>
    $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'ToolUse', requestId: id,
      props: { tool_use_id: id, tool: MESSAGE_TOOL, input, isRunning, isErrored, isInterrupted, output },
    } as never)
  const resultRow = ($: Engine, id: string, output: unknown, isErrored = false) =>
    $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'ToolResult', requestId: id,
      props: { tool_use_id: id, tool: MESSAGE_TOOL, output, isErrored },
    } as never)
  const message = ($: Engine, requestId: string, text: string) =>
    $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: true } })
  const bash = ($: Engine, id: string) =>
    $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'ToolUse', requestId: id,
      props: { tool_use_id: id, tool: 'Bash', input: { command: 'ls' }, isRunning: false, isErrored: false, isInterrupted: false, output: 'ok' },
    } as never)

  test('its call draws as a message, between runs of working record it breaks, and turns the view on', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    const before = await message($, 'r1', 'Reading the logs.')
    // Before any mark the view draws as the engine does.
    expect(await before.find({ type: 'Text', text: 'Reading the logs.' })).toBeDefined()
    const call = await callRow($, 'toolu_m1', { input: { text: 'Approve the **codesign** prompt now.' }, output: 'sent' })
    const after = await bash($, 'toolu_b1')

    expect(await call.find({ type: 'Text', text: '● message' })).toBeDefined()
    expect(await call.find({ type: 'Markdown', text: 'Approve the **codesign** prompt now.' })).toBeDefined()
    expect(await call.find({ type: 'Button' })).toBeUndefined()
    expect(await call.find({ type: 'Text', text: 'ToolUse' })).toBeUndefined()
    // The record before it folds once the view is on, and the call closes its run: the call after opens one of its own.
    expect(await before.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await before.find({ type: 'Text', text: 'Reading the logs.' })).toBeUndefined()
    expect(await after.find({ type: 'Button', text: 'working record' })).toBeDefined()
  })

  test('its result row draws nothing', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    await callRow($, 'toolu_m1', { input: { text: 'Done.' }, output: 'sent' })
    const result = await resultRow($, 'toolu_m1', 'sent')

    expect(await result.find({ type: 'Text' })).toBeUndefined()
    expect(await result.find({ type: 'Markdown' })).toBeUndefined()
    expect(await result.find({ type: 'Button' })).toBeUndefined()
  })

  test('a call whose input still streams draws the text so far, never the raw JSON', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    await message($, 'm0', '<message>Starting.</message>')
    const partial = await callRow($, 'toolu_m1', { input: '{"text": "Approve the dialog\\non the', isRunning: true })
    const empty = await callRow($, 'toolu_m2', { input: '{"te', isRunning: true })

    expect(await partial.find({ type: 'Text', text: '● message …' })).toBeDefined()
    expect(await partial.find({ type: 'Markdown', text: 'Approve the dialog\non the' })).toBeDefined()
    const texts = [...(await partial.findAll({ type: 'Text' })), ...(await empty.findAll({ type: 'Text' }))].map((t) => t.text)
    expect(texts.some((text) => text.includes('{'))).toBe(false)
    expect(await empty.find({ type: 'Markdown' })).toBeUndefined()
  })

  test('a refused, errored or interrupted call was not sent: it stays working record, its result too', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    await message($, 'm0', '<message>Starting.</message>')
    const refused = await callRow($, 'toolu_m1', { input: { text: 'Done.' }, isErrored: true, output: 'message is for the main conversation' })
    const result = await resultRow($, 'toolu_m1', 'message is for the main conversation', true)
    const interrupted = await callRow($, 'toolu_m2', { input: { text: 'Later.' }, isInterrupted: true, output: 'Interrupted' })
    const after = await resultRow($, 'toolu_m2', 'Interrupted')

    expect(await refused.find({ type: 'Markdown' })).toBeUndefined()
    expect(await refused.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await result.find({ type: 'Button' })).toBeUndefined()
    expect(await interrupted.find({ type: 'Markdown' })).toBeUndefined()
    expect(await after.find({ type: 'Markdown' })).toBeUndefined()

    // Unfolded, the run shows the engine's own rows.
    await refused.press({ key: 'to-human-toggle' })
    expect(await refused.find({ type: 'Text', text: 'ToolUse' })).toBeDefined()
    expect(await result.find({ type: 'Text', text: 'sent' })).toBeDefined()
  })

  test('the full transcript draws it as a message too, the rows around it as the engine does', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    const call = await callRow($, 'toolu_m1', { input: { text: 'Approve the **codesign** prompt now.' }, output: 'sent' })
    const band = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'AbovePrompt',
      props: { hasSurvey: false, isWorking: false, maxRows: 5, bodyColumns: 80, scroll: { offset: 0, bodyRows: 5 }, view: {} },
    })
    await band.press({ key: 'to-human-mode' })
    expect(await band.find({ type: 'Button', text: 'report only' })).toBeDefined()
    const result = await resultRow($, 'toolu_m1', 'sent')
    const after = await bash($, 'toolu_b1')

    expect(await call.find({ type: 'Text', text: '● message' })).toBeDefined()
    expect(await call.find({ type: 'Markdown', text: 'Approve the **codesign** prompt now.' })).toBeDefined()
    expect(await call.find({ type: 'Text', text: 'ToolUse' })).toBeUndefined()
    expect(await result.find({ type: 'Text' })).toBeUndefined()
    expect(await after.find({ type: 'Text', text: 'ToolUse' })).toBeDefined()
    expect(await after.find({ type: 'Button' })).toBeUndefined()
  })

  test('a module that starts over in a session whose only message went through the tool folds from its first answer', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    let rawAnswers = 0
    on('ui.render', (_, e) => {
      if (e.component !== 'AbovePrompt') rawAnswers += 1
      return { type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }
    })
    on('session.messages', () => ({
      value: [{
        role: 'assistant', text: '',
        toolUses: [{ tool_use_id: 'toolu_m1', tool: MESSAGE_TOOL, input: { text: 'Approve it.' }, result: 'sent', text: 'sent' }],
      }],
    }))
    on('session.id', () => ({ value: 's1' }))
    on('process.run', async () => ({ value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
    const row = await message($, 'r1', 'Reading.')

    expect(rawAnswers).toBe(0)
    expect(await row.find({ type: 'Button', text: 'working record' })).toBeDefined()
  })

  test('a refused call in the conversation is no mark', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    on('session.messages', () => ({
      value: [{
        role: 'assistant', text: '',
        toolUses: [{ tool_use_id: 'toolu_m1', tool: MESSAGE_TOOL, input: { text: 'Done.' }, text: 'refused', isError: true }],
      }],
    }))
    on('session.id', () => ({ value: 's1' }))
    on('process.run', async () => ({ value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
    const row = await message($, 'r1', 'Reading.')

    expect(await row.find({ type: 'Text', text: 'Reading.' })).toBeDefined()
  })
})
