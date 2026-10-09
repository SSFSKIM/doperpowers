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
      ui: {
        resolve: () => ({ Box: 'Box', Text: 'Text', Button: 'Button', Markdown: 'Markdown' }),
        invalidate: () => { calls.push('invalidate') },
        toast: () => { calls.push('toast') },
      },
      session: { messages: async () => [] },
      prompt: {
        read: async () => { calls.push('read'); return { text: '' } },
        fill: async () => { calls.push('fill'); return { isFilled: true } },
      },
    } as unknown as EngineInterface
    const text = '<to-human>One.</to-human>\n<need-input>Which branch?\n<choice>main</choice>\n</need-input>'
    const assistant = hooks.find((hook) => hook.matcher.component === 'AssistantMessage')!
    const terminal: Event = {
      surface: 'terminal', component: 'AssistantMessage', requestId: 'm1',
      props: { text, isFirstOfReply: true },
    }
    const bodies: unknown[] = []
    const report = await assistant.handler(engine, terminal, async (e) => {
      bodies.push((e.props as { text: string }).text)
      return { type: 'Text', children: [(e.props as { text: string }).text] }
    })
    expect(report).toMatchObject({ type: 'Box' })
    expect(bodies).toEqual(['One.', 'Which branch?'])

    // A marked terminal row primes the folding state and the question key:
    // otherwise a missing guard on AbovePrompt or a question press could
    // look like a pass-through simply because there was nothing to do yet.
    calls.length = 0
    for (const surface of ['desktop', 'vscode', 'mobile', undefined]) {
      await Promise.all(hooks.filter((hook) => hook.event !== 'prompt.submit').map(async (hook) => {
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
          ...(hook.event === 'ui.press' && { element: hook.matcher.element ?? 'need-input:m1:1:0' }),
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

    // A submission carries no surface and is not gated: the answer settles
    // the question, and the terminal's row reads it on its next draw.
    const submit = hooks.find((hook) => hook.event === 'prompt.submit')!
    const passed = Object.freeze({})
    expect(await submit.handler(engine, { text: 'Answering "Which branch?": main' }, async () => passed)).toBe(passed)
    expect(calls).toEqual(['invalidate'])
    const settled = await assistant.handler(engine, terminal, async (e) => ({ type: 'Text', children: [(e.props as { text: string }).text] }))
    const leaves = (node: unknown): string => typeof node === 'string' ? node
      : Array.isArray(node) ? node.map(leaves).join('')
      : node && typeof node === 'object' ? leaves((node as { children?: unknown }).children ?? Object.values(node)) : ''
    expect(leaves(settled)).toContain('answered: main')
    expect(envReads).toEqual(['MAWS_NATIVE_TO_HUMAN'])
  })
})
