import { describe, expect, mock, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

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
})
