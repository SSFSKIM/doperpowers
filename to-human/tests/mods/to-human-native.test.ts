import { describe, expect, mock, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import * as view from '../../hooks/mods/to-human'
import { registerToHuman } from '../../hooks/mods/to-human'

tier('user')

describe('MAWS native to-human', () => {
  test('the view steps aside for a non-empty value that is not a number of 9 or more, and draws for unset, empty and 9 on', () => {
    expect(view.MAWS_DRAWS_FROM).toBe(9)
    for (const value of ['1', '8', '8.9', '-1', 'native', 'nine', 'NaN']) expect(view.isMawsDrawing(value)).toBe(true)
    for (const value of [undefined, '', '9', '10', '9.5', '1e3']) expect(view.isMawsDrawing(value)).toBe(false)
  })

  for (const value of ['1', '8', 'native']) test(`at '${value}' every hook passes through unchanged off-terminal, while the terminal still draws the report`, async () => {
    // Capture the registered handlers, as compact.test.ts does, so an event
    // without a surface and next(e)'s identity can be checked too.
    type Event = Record<string, unknown>
    type Handler = (engine: EngineInterface, e: Event, next: (e: Event) => Promise<unknown>) => unknown
    const hooks: { event: string; matcher: Event; handler: Handler }[] = []
    const on = ((event: string, ...rest: unknown[]) => {
      hooks.push({
        event,
        matcher: rest.length > 1 ? rest[0] as Event : {},
        handler: rest[rest.length - 1] as Handler,
      })
    }) as unknown as On
    registerToHuman(on)

    const calls: string[] = []
    const envReads: string[] = []
    const engine = {
      env: { get: async (name: string) => { envReads.push(name); return value } },
      // The module's start-up read: a session with no mark sent and no transcript yet.
      session: { messages: async () => [], id: async () => 's1' },
      process: { run: async () => ({ exitCode: 1, stdout: '', stderr: '' }) },
      clock: { after: () => ({ cancel: () => {} }), now: async () => 0 },
      ui: {
        resolve: () => ({ Box: 'Box', Text: 'Text', Button: 'Button', Markdown: 'Markdown' }),
        invalidate: () => { calls.push('invalidate') },
        toast: () => { calls.push('toast') },
        log: () => {},
      },
    } as unknown as EngineInterface
    const text = '<message>One.</message>\n<need-input>Which branch?\n<choice>main</choice>\n</need-input>'
    const assistant = hooks.find((hook) => hook.matcher.component === 'AssistantMessage')!
    const terminal: Event = {
      surface: 'terminal', component: 'AssistantMessage', requestId: 'm1',
      props: { text, isFirstOfReply: true },
    }
    const bodies: unknown[] = []
    // A next as the engine hands it: the chain beneath, and the dispatch's signal.
    const report = await assistant.handler(engine, terminal, Object.assign(async (e: Event) => {
      bodies.push((e.props as { text: string }).text)
      return { type: 'Text', children: [(e.props as { text: string }).text] }
    }, { signal: new AbortController().signal }))
    expect(report).toMatchObject({ type: 'Box' })
    // The terminal draws each body as its own Markdown; nothing is handed back.
    expect(JSON.stringify(report)).toContain('"One."')
    expect(bodies).toEqual([])

    // A marked terminal row primes the folding state: otherwise a missing
    // guard on AbovePrompt could look like a pass-through simply because
    // there was nothing to do yet.
    calls.length = 0
    const gated = (event: string) => event === 'ui.render' || event === 'ui.press' || event === 'command.run'
    const drawing = hooks.filter((hook) => gated(hook.event))
    for (const surface of ['desktop', 'vscode', 'mobile', undefined]) {
      await Promise.all(drawing.map(async (hook) => {
        const e: Event = {
          ...(surface !== undefined && { surface }),
          ...hook.matcher,
          requestId: 'r1',
          props: {
            text, isFirstOfReply: true, hasSurvey: false,
            origin: { kind: 'peer' }, tool: 'Bash',
            calls: [{ tool_use_id: 't1', tool: 'Bash', input: {} }],
            isExpanded: false,
          },
          ...(hook.event === 'ui.press' && { element: hook.matcher.element }),
        }
        const result = Object.freeze({ marker: 'next result' })
        const received: Event[] = []
        expect(await hook.handler(engine, e, async (input) => {
          received.push(input)
          return result
        })).toBe(result)
        expect(received.length).toBe(1)
        expect(received[0]).toBe(e)
      }))
    }
    expect(calls).toEqual([])
    // Every hook but the view's four and the run tracker's four draws or
    // answers the view's command, so every one is gated: none is left that
    // answers a question or a prompt. These draw nothing: the view's learn
    // whether a mark was sent, where each row stands in the transcript, which
    // rows are API errors and where a step ends, for the terminal's report; the
    // tracker's follow the kept rows into runs and publish them in `$.state`
    // (folds.tsx), handing every event on.
    expect(hooks.map((hook) => hook.event).filter((event) => !gated(event))).toEqual([
      'session.start', 'classic.SessionStart', 'session.append', 'turn.complete',
      'session.start', 'session.append', 'turn.complete', 'classic.SessionStart',
    ])
    expect(envReads).toEqual(['MAWS_NATIVE_TO_HUMAN'])
  })

  // From 9 the client reads the view's drawing: the mod draws on every surface, as it does in a terminal.
  const PLUGIN = 'to-human'
  const band = { hasSurvey: false, isWorking: false, isCollapsed: false, maxRows: 5, bodyColumns: 80, scroll: { offset: 0, bodyRows: 5 }, view: {} }
  for (const value of ['9', '10']) {
    for (const surface of ['desktop', 'vscode', 'mobile'] as const) {
      test(`at '${value}' on ${surface} the view draws: the report, a folded record, the band after a mark, and both presses act`, async ($, on) => {
        mock.env(on, { MAWS_NATIVE_TO_HUMAN: value })
        mock.store(on)
        on('ui.render', (_, e) => ({ type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }))
        const message = (requestId: string, text: string) =>
          $.ui.mount({ plugin: PLUGIN, surface, component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: true } })
        const marked = await message('m1', '<message>One.</message>')
        expect(await marked.find({ type: 'Markdown', text: 'One.' })).toBeDefined()
        expect(await marked.find({ type: 'Text', text: '<message>One.</message>' })).toBeUndefined()
        const record = await message('r1', 'Working.')
        expect(await record.find({ type: 'Button', text: 'working record' })).toBeDefined()
        expect(await record.find({ type: 'Text', text: 'Working.' })).toBeUndefined()
        const above = await $.ui.mount({ plugin: PLUGIN, surface, component: 'AbovePrompt', props: band })
        expect(await above.find({ type: 'Button', text: 'full transcript' })).toBeDefined()

        await record.press({ key: 'to-human-toggle' })
        expect(await record.find({ type: 'Text', text: 'Working.' })).toBeDefined()
        expect(await record.find({ type: 'Button', text: 'fold to report' })).toBeDefined()
        await above.press({ key: 'to-human-mode' })
        expect(await above.find({ type: 'Button', text: 'report only' })).toBeDefined()
        expect(await marked.find({ type: 'Text', text: '<message>One.</message>' })).toBeDefined()
      })
    }
  }

  // MAWS asks a row the transcript holds no record of (a turn's closing line,
  // a notice the host made) under `<anchor>~<tag>`, its anchor the nearest
  // row before it the file holds: the view places it right after that row.
  // Each is asked alone here, with no other row of its run asked first, as a
  // client asks whichever rows it has in view.
  const PROMPT = 'u0'
  const LATER = 'u1'
  const THINKING = 'aaaaaaaa-1111-4222-8333-444444444444'
  const TRANSCRIPT = [PROMPT, 'm1', 'r1', 'toolu_1', 'm2', THINKING, 'toolu_2', 'm3', LATER, 'r4', 'm4']
  const listed = TRANSCRIPT.map((id) => (id.startsWith('toolu_') ? `"type":"tool_use","id":"${id}"` : `"uuid":"${id}"`)).join('\n')
  /** A session MAWS resumed at 9 whose transcript holds a mark, its rows listed by the transcript search. */
  const resumed = (on: On) => {
    mock.env(on, { MAWS_NATIVE_TO_HUMAN: '9' })
    mock.store(on)
    on('ui.render', (_, e) => ({ type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }))
    on('session.messages', () => ({ value: [{ role: 'assistant', text: '<message>Earlier.</message>', toolUses: [] }] }))
    on('session.id', () => ({ value: 's1' }))
    on('process.run', async (_, e) => {
      const script = e.argv[2] ?? ''
      const answer = (stdout: string, exitCode = 0) => ({ value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
      if (script.startsWith('tail -c')) return answer(listed.slice(Number(e.argv[5]) - 1, Number(e.argv[5]) - 1 + Number(e.argv[6])))
      if (script.startsWith('mktemp')) return answer('/tmp/to-human-places.test\n')
      return answer('')
    })
  }
  const surface = 'desktop' as const
  const note = ($: Engine, requestId: string, text: string, extra: Record<string, unknown> = {}) =>
    $.ui.mount({ plugin: PLUGIN, surface, component: 'AssistantMessage', requestId, props: { text, isFirstOfReply: false, ...extra } })
  const notice = ($: Engine, requestId: string, origin: Record<string, unknown>, extra: Record<string, unknown> = {}) =>
    $.ui.mount({ plugin: PLUGIN, surface, component: 'UserMessage', requestId, props: { text: 'The nightly check ran.', origin, isExpanded: false, ...extra } } as never)
  const turnLine = ($: Engine, requestId: string) =>
    $.ui.mount({ plugin: PLUGIN, surface, component: 'TurnDuration', requestId, props: { word: 'Baked', durationMs: 3000, isExpanded: true } } as never)
  const bandOf = ($: Engine) => $.ui.mount({ plugin: PLUGIN, surface, component: 'AbovePrompt', props: band })

  for (const [origin, extra] of [
    [{ kind: 'task-notification' }, { task: { id: 'b1', status: 'completed', toolUseId: 'toolu_1' } }],
    [{ kind: 'scheduled-trigger' }, {}],
    [{ kind: 'plugin', server: 'sminos' }, {}],
    [{ kind: 'peer' }, { from: { name: 'reviewer' } }],
  ] as const) {
    test(`an ask under <anchor>~<tag> (${origin.kind}) folds with the run its anchor is in, placed right after it`, async ($, on) => {
      resumed(on)
      const ask = await notice($, 'r1~n1', origin, extra)
      // Alone, it is the one drawn row of its run: the run's button, not its own text.
      expect(await ask.find({ type: 'Button', text: 'working record' })).toBeDefined()
      expect(await ask.find({ type: 'Text', text: 'The nightly check ran.' })).toBeUndefined()
      // Its anchor, asked after, stands before it and takes the run's button.
      const anchor = await note($, 'r1', 'Reading.')
      expect(await anchor.find({ type: 'Button', text: 'working record' })).toBeDefined()
      expect(await ask.find({ type: 'Button' })).toBeUndefined()
      expect(await ask.find({ type: 'Text', text: 'The nightly check ran.' })).toBeUndefined()
      await anchor.press({ key: 'to-human-toggle' })
      expect(await ask.find({ type: 'Text', text: 'The nightly check ran.' })).toBeDefined()
    })
  }

  test('an ask under <anchor>~<tag> after a row the person reads begins the run there', async ($, on) => {
    resumed(on)
    const ask = await notice($, 'm1~n1', { kind: 'scheduled-trigger' })
    expect(await ask.find({ type: 'Button', text: 'working record' })).toBeDefined()
    const marked = await note($, 'm1', '<message>Looking.</message>')
    const after = await note($, 'r1', 'Reading.')
    expect(await marked.find({ type: 'Button' })).toBeUndefined()
    expect(await ask.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await after.find({ type: 'Button' })).toBeUndefined()
    expect(await after.find({ type: 'Text', text: 'Reading.' })).toBeUndefined()
  })

  test("a turn's line under <anchor>~turn is hidden in a folded report, asked alone", async ($, on) => {
    resumed(on)
    const line = await turnLine($, `${PROMPT}~turn`)
    expect(await line.find({ type: 'Text', text: 'TurnDuration' })).toBeUndefined()
  })

  test("a turn's line under <anchor>~turn shows while a record of its turn is open, and only of its turn", async ($, on) => {
    resumed(on)
    // A run of the next turn, opened, leaves this turn's line hidden.
    const later = await note($, 'r4', 'Later.')
    await later.press({ key: 'to-human-toggle' })
    const line = await turnLine($, `${PROMPT}~turn`)
    expect(await line.find({ type: 'Text', text: 'TurnDuration' })).toBeUndefined()
    // A run of its own turn, opened, shows it; folded again, it hides.
    const record = await note($, 'r1', 'Reading.')
    await record.press({ key: 'to-human-toggle' })
    expect(await line.find({ type: 'Text', text: 'TurnDuration' })).toBeDefined()
    await record.press({ key: 'to-human-toggle' })
    expect(await line.find({ type: 'Text', text: 'TurnDuration' })).toBeUndefined()
  })

  test("a turn's line anchored in a run shows with that run open", async ($, on) => {
    resumed(on)
    const record = await note($, 'r1', 'Reading.')
    await record.press({ key: 'to-human-toggle' })
    const line = await turnLine($, 'r1~turn')
    expect(await line.find({ type: 'Text', text: 'TurnDuration' })).toBeDefined()
  })

  test("a turn's line under <anchor>~turn shows in the full transcript", async ($, on) => {
    resumed(on)
    const above = await bandOf($)
    await above.press({ key: 'to-human-mode' })
    const line = await turnLine($, `${PROMPT}~turn`)
    expect(await line.find({ type: 'Text', text: 'TurnDuration' })).toBeDefined()
  })

  test('a thought (a summary block) is a record row: it folds with its run, opens with it, and stays in the full transcript', async ($, on) => {
    resumed(on)
    // Its id is its response's uuid qualified by the block, as a text block's is.
    const thought = await note($, `${THINKING.slice(0, 24)}000000000000`, 'Weighing the two fixes.', { isSummary: true })
    expect(await thought.find({ type: 'Button', text: 'working record' })).toBeDefined()
    expect(await thought.find({ type: 'Text', text: 'Weighing the two fixes.' })).toBeUndefined()
    await thought.press({ key: 'to-human-toggle' })
    expect(await thought.find({ type: 'Text', text: 'Weighing the two fixes.' })).toBeDefined()
    await thought.press({ key: 'to-human-toggle' })
    const above = await bandOf($)
    await above.press({ key: 'to-human-mode' })
    expect(await thought.find({ type: 'Text', text: 'Weighing the two fixes.' })).toBeDefined()
  })
})
