import type { On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import { DESCRIPTION, EMPTY_REFUSAL, FINAL_ANSWER, INPUT_SCHEMA, MESSAGE_TOOL, SENT, SUBAGENT_REFUSAL, TO_HUMAN_STYLE, readMessage } from '../../hooks/mods/message'

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
      properties: {
        text: { type: 'string', description: 'The message, in Markdown.' },
        final: { type: 'boolean', description: expect.any(String) },
      },
      required: ['text'],
    })
  })

  for (const env of [{}, { SMNS_INTERNAL: '1' } as Record<string, string>, { MAWS_NATIVE_TO_HUMAN: '7' }, { MAWS_NATIVE_TO_HUMAN: '' }, { MAWS_NATIVE_TO_HUMAN: 'native' }]) {
    test(`a headless session registers none: nobody reads its report (${JSON.stringify(env)})`, async ($, on) => {
      const { registered } = engine(on, { env })
      await $.session.start({ cwd: '/w', surface: null, isInteractive: false })

      expect(registered).toEqual([])
    })
  }

  for (const advertised of ['8', '9']) {
    test(`a headless launch of a MAWS that advertises ${advertised}, which offers no tool of its own and reads the report, registers it`, async ($, on) => {
      const { registered } = engine(on, { env: { MAWS_NATIVE_TO_HUMAN: advertised } })
      await $.session.start({ cwd: '/w', surface: null, isInteractive: false })

      expect(registered.map((r) => r.tool)).toEqual([MESSAGE_TOOL])
    })
  }

  test('a headless MAWS launch under another output style registers none', async ($, on) => {
    const { registered } = engine(on, { env: { MAWS_NATIVE_TO_HUMAN: '8' }, style: 'default' })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: false })

    expect(registered).toEqual([])
  })

  for (const advertised of ['1', '7', ' 7 ']) {
    test(`an interactive launch of a MAWS that advertises ${JSON.stringify(advertised)} registers none: it registers its own`, async ($, on) => {
      const { registered } = engine(on, { env: { MAWS_NATIVE_TO_HUMAN: advertised } })
      await $.session.start({ cwd: '/w', surface: null, isInteractive: true })

      expect(registered).toEqual([])
    })
  }

  for (const advertised of ['8', '9', '', 'native']) {
    test(`an interactive launch whose MAWS_NATIVE_TO_HUMAN is ${JSON.stringify(advertised)} registers it: from 8 on MAWS offers none of its own`, async ($, on) => {
      const { registered } = engine(on, { env: { MAWS_NATIVE_TO_HUMAN: advertised } })
      await $.session.start({ cwd: '/w', surface: null, isInteractive: true })

      expect(registered.map((r) => r.tool)).toEqual([MESSAGE_TOOL])
    })
  }

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

  test('in a MAWS session, whose notification surface is MAWS, a call is sent and notifies no one', async ($, on) => {
    const { clock, registered, notified } = engine(on, { env: { MAWS_NATIVE_TO_HUMAN: '8' } })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    expect(registered.map((r) => r.tool)).toEqual([MESSAGE_TOOL])
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


type Block = Record<string, unknown>

const USAGE = { input_tokens: 40_000, output_tokens: 12, cache_read_input_tokens: 0, cache_creation_input_tokens: 0, model: 'claude-haiku' }
const CLOSING = 'Done, as the message says.'

/**
 * The model beneath the plugin, for `turn.step`: a request, recorded by its
 * step, answered with a closing text. A row the test keeps is the kit's to
 * keep, as the engine's is.
 */
function model(on: On) {
  const requested: number[] = []
  on('turn.step', async function* (_, e) {
    requested.push(e.index)
    yield { kind: 'text', index: 0, text: CLOSING }
    yield { kind: 'stop', stopReason: 'end_turn', usage: USAGE }
    return { turnId: e.turnId, index: e.index, answer: CLOSING, toolUses: [], stopReason: 'end_turn', usage: USAGE }
  })
  return { requested }
}

/** One step of turn `t1` through every hook: the chunks that came out, and its result. */
async function step($: Engine, index: number, agentId?: string) {
  const stream = $.turn.step({ turnId: 't1', index, model: 'haiku', messageCount: 3, ...(agentId !== undefined && { agentId }) })
  const chunks: unknown[] = []
  for (let read = await stream.next(); ; read = await stream.next()) {
    if (read.done === true) {
      return { chunks, result: read.value }
    }
    chunks.push(read.value)
  }
}

let rows = 0
/** A row the main loop keeps, raised as the engine raises it; `agentId` for a subagent's. */
const kept = ($: Engine, door: string, message: Block, agentId?: string) =>
  $.session.append({ door, uuid: `row-${++rows}`, origin: { kind: 'engine' }, message, ...(agentId !== undefined && { agentId }) } as never)
const messageCall = (id: string, input: Block): Block => ({ type: 'tool_use', id, name: MESSAGE_TOOL, input })
const response = (...blocks: Block[]): Block => ({ type: 'assistant', role: 'assistant', content: blocks })
const results = (...blocks: Block[]): Block => ({ type: 'user', role: 'user', content: blocks })
const toolResult = (id: string, content: unknown = SENT, extra: Block = {}): Block => ({ type: 'tool_result', tool_use_id: id, content, ...extra })
const attachment = (name: string, text: string): Block => ({ type: 'attachment', name, role: 'user', isMeta: true, content: [{ type: 'text', text }] })
// What the engine puts beside every request after a tool result under the style (2.1.312).
const standing = async ($: Engine) => {
  await kept($, 'attachment', attachment('total_tokens_reminder', '<total_tokens>14999792 tokens left</total_tokens>'))
  await kept($, 'attachment', attachment('output_style', 'doperpowers:to-human output style is active.'))
}

/** A turn whose first response calls the message tool with `input`, its result `result`. */
async function messageTurn($: Engine, input: Block, result: Block = toolResult('toolu_f1')) {
  await step($, 0)
  await kept($, 'response', response({ type: 'text', text: 'Telling them.' }, messageCall('toolu_f1', input)))
  await kept($, 'tool-result', results(result))
}

describe('a final message', () => {
  test('sent alone, it ends the turn: the step after it is answered here, made up, with no request', async ($, on) => {
    engine(on)
    const { requested } = model(on)
    await messageTurn($, { text: 'All done: the report is in docs/.', final: true })
    await standing($)

    const { chunks, result } = await step($, 1)

    expect(requested).toEqual([0])
    expect(chunks).toEqual([
      { kind: 'text', index: 0, text: FINAL_ANSWER },
      { kind: 'stop', stopReason: 'end_turn', usage: null },
    ])
    expect(result).toEqual({ turnId: 't1', index: 1, answer: FINAL_ANSWER, toolUses: [], stopReason: 'end_turn', usage: null })
    expect(FINAL_ANSWER).toBe('Message sent to the human.')
    // The made-up response is kept as any response is, and the step after it is the model's again.
    await kept($, 'response', response({ type: 'text', text: FINAL_ANSWER }))
    await step($, 2)
    expect(requested).toEqual([0, 2])
  })

  test('beside another tool, it lets the request go: the model reads that result', async ($, on) => {
    engine(on)
    const { requested } = model(on)
    await step($, 0)
    await kept($, 'response', response(messageCall('toolu_f1', { text: 'Building; my last word.', final: true }), { type: 'tool_use', id: 'toolu_b1', name: 'Bash', input: { command: 'make' } }))
    await kept($, 'tool-result', results(toolResult('toolu_f1')))
    await kept($, 'tool-result', results(toolResult('toolu_b1', 'make: done')))

    const { result } = await step($, 1)

    expect(requested).toEqual([0, 1])
    expect(result).toMatchObject({ answer: CLOSING, usage: USAGE })
  })

  test('refused, or beside a message refused, it lets the request go: the model reads why', async ($, on) => {
    engine(on)
    const { requested } = model(on)
    expect(await $.tool.call({ tool: MESSAGE_TOOL, tool_use_id: 'toolu_f1', text: '  ', final: true } as never)).toEqual({ deny: EMPTY_REFUSAL })
    await messageTurn($, { text: '  ', final: true }, toolResult('toolu_f1', EMPTY_REFUSAL, { is_error: true }))
    await step($, 1)
    await step($, 0)
    await kept($, 'response', response(messageCall('toolu_f1', { text: 'Done.', final: true }), messageCall('toolu_m2', { text: '' })))
    await kept($, 'tool-result', results(toolResult('toolu_f1'), toolResult('toolu_m2', EMPTY_REFUSAL, { is_error: true })))
    await step($, 1)

    expect(requested).toEqual([0, 1, 0, 1])
  })

  test('with final false or absent, the request goes', async ($, on) => {
    engine(on)
    const { requested } = model(on)
    await messageTurn($, { text: 'Halfway.', final: false })
    await step($, 1)
    await messageTurn($, { text: 'Halfway.' })
    await step($, 1)

    expect(requested).toEqual([0, 1, 0, 1])
  })

  test('anything else kept beside its result (a prompt typed mid-turn, a hook\'s context, more in the result) lets the request go', async ($, on) => {
    engine(on)
    const { requested } = model(on)
    const final = { text: 'Done.', final: true }
    await messageTurn($, final)
    await standing($)
    await kept($, 'attachment', attachment('queued_command', 'wait, one more thing'))
    await step($, 1)
    await messageTurn($, final)
    await kept($, 'hook-context', attachment('hook_additional_context', 'An answer arrived: yes.'))
    await step($, 1)
    await messageTurn($, final, toolResult('toolu_f1', [{ type: 'text', text: SENT }, { type: 'text', text: 'An answer arrived: yes.' }]))
    await step($, 1)
    // A result as the engine may hold it, one text block, is still the message sent; a row no
    // request carries, or one that carries no block, is nothing.
    await messageTurn($, final, toolResult('toolu_f1', [{ type: 'text', text: SENT }]))
    await kept($, 'notice', { type: 'system', name: 'turn_duration', content: [{ type: 'text', text: '3s' }] })
    await kept($, 'hook-context', { type: 'attachment', name: 'hook_success', role: 'user', isMeta: true, content: [] })
    await standing($)
    await step($, 1)

    expect(requested).toEqual([0, 1, 0, 1, 0, 1, 0])
  })

  test("a subagent's rows and steps pass through, and a turn's first step is never answered here", async ($, on) => {
    engine(on)
    const { requested } = model(on)
    await messageTurn($, { text: 'Done.', final: true })
    // A subagent's loop, running beside: its rows and its step are its own.
    await kept($, 'response', response({ type: 'tool_use', id: 'toolu_a1', name: 'Bash', input: { command: 'ls' } }), 'agent-1')
    await step($, 4, 'agent-1')
    await step($, 1)
    expect(requested).toEqual([0, 4])
    // A turn cut short after the message: the next turn's first step follows the person's prompt.
    await messageTurn($, { text: 'Done.', final: true })
    await step($, 0)
    expect(requested).toEqual([0, 4, 0, 0])
  })
})
