import type { On } from 'claude-code'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import { DESCRIPTION, EMPTY_REFUSAL, INPUT_SCHEMA, MESSAGE_TOOL, SENT, SUBAGENT_REFUSAL, TO_HUMAN_STYLE, readMessage } from '../../hooks/mods/message'

tier('user')

type Registered = { plugin: string; name: string; description: string; inputSchema: unknown; tool: string }

/**
 * The engine beneath the plugin: `tool.register` answered as the engine names
 * a plugin's tool (`mcp__<plugin>__<name>`, every character but
 * `[a-zA-Z0-9_-]` replaced, bundle 2.1.304's `F5`), `tool.describe` with the
 * engine's own placement (an MCP tool behind ToolSearch), `ui.notify` recorded,
 * and `/config`'s output style row holding `style`, as a live session's
 * `$.config.list()` reads it (2.1.305: key `outputStyle`, value the style's
 * name, `doperpowers:to-human` for the plugin's).
 */
function engine(
  on: On,
  { env = {}, style = TO_HUMAN_STYLE, notify = () => ({ value: { isSent: true, channel: 'terminal_bell' } }) }: { env?: Record<string, string>; style?: string | null; notify?: () => unknown } = {},
) {
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
  // `style: null`: the read fails.
  on('config.list', () =>
    style === null
      ? ({ deny: 'no config here' } as never)
      : { value: [{ key: 'outputStyle', label: 'Output style', kind: 'choice', value: style, options: ['default'], provider: { plugin: 'engine', tier: 'core' }, isLocked: false }] },
  )
  const logged: string[] = []
  on('ui.log', (_, e) => (logged.push(e.text), { value: undefined }))
  return { clock, registered, notified, logged }
}

const call = (text: unknown, agentId?: string) =>
  ({ tool: MESSAGE_TOOL, tool_use_id: 'toolu_m1', text, ...(agentId !== undefined && { agentId }) }) as never

describe('the message tool', () => {
  test('an interactive session under the to-human style registers it as the contract names it, under its full name', async ($, on) => {
    const { registered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })

    expect(registered).toEqual([{ plugin: 'to-human', name: 'message', description: DESCRIPTION, inputSchema: INPUT_SCHEMA, tool: MESSAGE_TOOL }])
    expect(MESSAGE_TOOL).toBe('mcp__to-human__message')
    expect(TO_HUMAN_STYLE).toBe('doperpowers:to-human')
    expect(DESCRIPTION).toBe('Send the human a message.')
    expect(INPUT_SCHEMA).toEqual({
      type: 'object',
      properties: { text: { type: 'string', description: 'The message, in Markdown.' } },
      required: ['text'],
    })
  })

  test('a headless session registers none', async ($, on) => {
    const { registered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: false })

    expect(registered).toEqual([])
  })

  test('an interactive MAWS launch registers none: MAWS registers its own', async ($, on) => {
    const { registered } = engine(on, { env: { MAWS_NATIVE_TO_HUMAN: '1' } })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })

    expect(registered).toEqual([])
  })

  test('an interactive session under another output style registers none: the rule for the tool is the style\'s', async ($, on) => {
    const { registered } = engine(on, { style: 'default' })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })

    expect(registered).toEqual([])
  })

  test('a session whose output style cannot be read registers none, and says why in the debug log', async ($, on) => {
    const { registered, logged } = engine(on, { style: null })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })

    expect(registered).toEqual([])
    expect(logged.some((text) => text.includes('output style could not be read'))).toBe(true)
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
    const { clock, notified } = engine(on, { env: { SMNS_INTERNAL: '1' } })
    expect(await $.tool.call(call('Done.'))).toEqual({ result: SENT })
    await clock.settle()

    expect(notified).toEqual([])
  })

  test('a notification that never settles does not hold the call', async ($, on) => {
    const { clock } = engine(on, { notify: () => new Promise<never>(() => {}) })

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
