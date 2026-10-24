import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import { registerToHuman } from '../../hooks/mods/to-human'

tier('user')

describe('MAWS native to-human', () => {
  test('the report draws on every surface under MAWS as without it, and the view never reads the flag', async () => {
    // Capture the registered handlers, as compact.test.ts does, so next(e)'s
    // use can be checked on a surface the kit does not mount.
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

    // MAWS's launches set MAWS_NATIVE_TO_HUMAN for its own message and ask
    // tools; the view is what MAWS shows, so it draws there as anywhere.
    const envReads: string[] = []
    const engine = {
      env: { get: async (name: string) => { envReads.push(name); return '1' } },
      // The module's start-up read: a session with no mark sent and no transcript yet.
      session: { messages: async () => [], id: async () => 's1' },
      process: { run: async () => ({ exitCode: 1, stdout: '', stderr: '' }) },
      clock: { after: () => ({ cancel: () => {} }), now: async () => 0 },
      ui: {
        resolve: () => ({ Box: 'Box', Text: 'Text', Button: 'Button', Markdown: 'Markdown' }),
        invalidate: () => {},
        toast: () => {},
      },
    } as unknown as EngineInterface
    const text = '<message>One.</message>\nWorking notes.'
    const assistant = hooks.find((hook) => hook.matcher.component === 'AssistantMessage')!
    for (const surface of ['terminal', 'desktop', 'vscode', 'mobile']) {
      const bodies: unknown[] = []
      const report = await assistant.handler(engine, {
        surface, component: 'AssistantMessage', requestId: `m-${surface}`,
        props: { text, isFirstOfReply: true },
      }, Object.assign(async (e: Event) => {
        bodies.push((e.props as { text: string }).text)
        return { type: 'Text', children: [(e.props as { text: string }).text] }
      }, { signal: new AbortController().signal }))
      // Each surface draws the span's body as its own Markdown, the record
      // behind its button; nothing is handed back to the engine.
      expect(report).toMatchObject({ type: 'Box' })
      expect(JSON.stringify(report)).toContain('"One."')
      expect(JSON.stringify(report)).not.toContain('Working notes.')
      expect(bodies).toEqual([])
    }
    expect(envReads).toEqual([])
  })
})
