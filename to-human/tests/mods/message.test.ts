import type { On } from 'claude-code'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import { DESCRIPTION, EMPTY_REFUSAL, INPUT_SCHEMA, MESSAGE_TOOL, SENT, SUBAGENT_REFUSAL, readMessage } from '../../hooks/mods/message'

tier('user')

type Registered = { plugin: string; name: string; description: string; inputSchema: unknown; tool: string }

/**
 * The engine beneath the plugin: `tool.register` answered as the engine names
 * a plugin's tool (`mcp__<plugin>__<name>`, every character but
 * `[a-zA-Z0-9_-]` replaced, bundle 2.1.304's `F5`), `tool.describe` with the
 * engine's own placement (an MCP tool behind ToolSearch), `ui.notify` recorded.
 */
function engine(on: On, env: Record<string, string> = {}, notify: () => unknown = () => ({ value: { isSent: true, channel: 'terminal_bell' } })) {
  mock.env(on, env)
  mock.store(on)
  const clock = mock.clock(on)
  const registered: Registered[] = []
  const notified: string[] = []
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('tool.register', (_, e, next) => {
    const plugin = next.origin.plugin.replace(/[^a-zA-Z0-9_-]/g, '_')
    const tool = `mcp__${plugin}__${e.name}`
    registered.push({ plugin: next.origin.plugin, name: e.name, description: e.description, inputSchema: e.inputSchema, tool })
    return { value: { tool } }
  })
  on('tool.describe', (_, e) => ({ description: e.description, isDeferred: true }))
  on('ui.notify', (_, e) => (notified.push(e.text), notify() as never))
  return { clock, registered, notified }
}

const call = (text: unknown, agentId?: string) =>
  ({ tool: MESSAGE_TOOL, tool_use_id: 'toolu_m1', text, ...(agentId !== undefined && { agentId }) }) as never

describe('the message tool', () => {
  test('an interactive session registers it as the contract names it, under its full name', async ($, on) => {
    const { registered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })

    expect(registered).toEqual([{ plugin: 'to-human', name: 'message', description: DESCRIPTION, inputSchema: INPUT_SCHEMA, tool: MESSAGE_TOOL }])
    expect(MESSAGE_TOOL).toBe('mcp__to-human__message')
    expect(DESCRIPTION).toBe(
      'Send the human a message now, word for word. Use it for a message you send before another tool call, in the same response as that call; a message at the end of your turn stays a <message> span.',
    )
    expect(INPUT_SCHEMA).toEqual({
      type: 'object',
      properties: { text: { type: 'string', description: 'The message, in Markdown: what you would write inside <message>…</message>.' } },
      required: ['text'],
    })
  })

  test('a headless session, and a MAWS launch, register none', async ($, on) => {
    const { registered } = engine(on, { MAWS_NATIVE_TO_HUMAN: '1' })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: false })

    expect(registered).toEqual([])
  })

  test('it is always loaded: its description keeps it out of ToolSearch', async ($, on) => {
    engine(on)
    const described = await $.tool.describe({ tool: MESSAGE_TOOL, description: DESCRIPTION, isDeferred: true, provider: { plugin: 'to-human', tier: 'user' } })

    expect(described).toEqual({ description: DESCRIPTION, isDeferred: false })
  })

  test('a main-conversation call is sent, and notifies the person with its preview', async ($, on) => {
    const { clock, notified } = engine(on)
    const result = await $.tool.call(call('Approve the **codesign** prompt on the mini at 07:15.\n\nI keep working meanwhile.'))
    await clock.settle()

    expect(result).toEqual({ result: SENT })
    expect(SENT).toBe('sent')
    expect(notified).toEqual(['Approve the codesign prompt on the mini at 07:15. I keep working meanwhile.'])
  })

  test("a subagent's call is refused, and notifies no one", async ($, on) => {
    const { clock, notified } = engine(on)
    const result = await $.tool.call(call('Done.', 'agent-1'))
    await clock.settle()

    expect(result).toEqual({ deny: SUBAGENT_REFUSAL })
    expect(SUBAGENT_REFUSAL).toBe(
      'message is for the main conversation; a subagent reaches the human through the session that dispatched it: put this in your report.',
    )
    expect(notified).toEqual([])
  })

  test('a call with no text to send is refused, and notifies no one', async ($, on) => {
    const { clock, notified } = engine(on)
    expect(await $.tool.call(call('  \n'))).toEqual({ deny: EMPTY_REFUSAL })
    expect(await $.tool.call(call(undefined))).toEqual({ deny: EMPTY_REFUSAL })
    await clock.settle()

    expect(notified).toEqual([])
  })

  test('in an internal fork of sminos a call is sent and notifies no one', async ($, on) => {
    const { clock, notified } = engine(on, { SMNS_INTERNAL: '1' })
    expect(await $.tool.call(call('Done.'))).toEqual({ result: SENT })
    await clock.settle()

    expect(notified).toEqual([])
  })

  test('a notification that never settles does not hold the call', async ($, on) => {
    const { clock } = engine(on, {}, () => new Promise<never>(() => {}))

    const sent = $.tool.call(call('Held.')).then(() => 'sent' as const)
    const held = clock.sleep(1000).then(() => 'held' as const)
    void clock.advance(1000)

    expect(await Promise.race([sent, held])).toBe('sent')
  })
})

describe('readMessage', () => {
  test('reads a whole input, and a streaming one as the text so far, never as raw JSON', () => {
    expect(readMessage({ text: 'Done.' })).toEqual({ text: 'Done.', isWhole: true })
    expect(readMessage('{"text": "Line one.\\nLine \\"two\\"')).toEqual({ text: 'Line one.\nLine "two"', isWhole: false })
    expect(readMessage('{"text":"caf\\u00e9 \\u')).toEqual({ text: 'café ', isWhole: false })
    expect(readMessage('{"text":"ends in an escape\\')).toEqual({ text: 'ends in an escape', isWhole: false })
    expect(readMessage('{"text":"whole"}')).toEqual({ text: 'whole', isWhole: true })
    expect(readMessage('{"te')).toBeUndefined()
    expect(readMessage({})).toBeUndefined()
    expect(readMessage(undefined)).toBeUndefined()
  })
})
