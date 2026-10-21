import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import { registerToHuman } from '../../hooks/mods/to-human'

tier('user')

describe('MAWS native to-human', () => {
  test('every hook passes through unchanged off-terminal, while the terminal still draws the report', async () => {
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
      env: { get: async (name: string) => { envReads.push(name); return '1' } },
      // The module's start-up read: a session with no mark sent and no transcript yet.
      session: { messages: async () => [], id: async () => 's1' },
      process: { run: async () => ({ exitCode: 1, stdout: '', stderr: '' }) },
      ui: {
        resolve: () => ({ Box: 'Box', Text: 'Text', Button: 'Button', Markdown: 'Markdown' }),
        invalidate: () => { calls.push('invalidate') },
        toast: () => { calls.push('toast') },
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
    }, { signal: { aborted: false } }))
    expect(report).toMatchObject({ type: 'Box' })
    // The terminal draws each body as its own Markdown; nothing is handed back.
    expect(JSON.stringify(report)).toContain('"One."')
    expect(bodies).toEqual([])

    // A marked terminal row primes the folding state: otherwise a missing
    // guard on AbovePrompt could look like a pass-through simply because
    // there was nothing to do yet.
    calls.length = 0
    const gated = (event: string) => event === 'ui.render' || event === 'ui.press'
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
    // Every hook but three draws, so every one is gated: none is left that
    // answers a question or a prompt. The three draw nothing: they learn
    // where each row stands in the transcript (`classic.SessionStart`,
    // `session.append`) and an error's text (`turn.complete`), for the
    // terminal's report.
    expect(hooks.map((hook) => hook.event).filter((event) => !gated(event))).toEqual(['classic.SessionStart', 'session.append', 'turn.complete'])
    expect(envReads).toEqual(['MAWS_NATIVE_TO_HUMAN'])
  })
})
