import type { On } from 'claude-code'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import { TO_HUMAN_STYLE } from '../../hooks/mods/message'
import { REMINDER, REMIND_AT, pointOf } from '../../hooks/mods/reminder'

tier('user')

/**
 * The engine beneath the plugin: the message tool registered as the engine
 * names it, `/config`'s output style, the context figure `$.session.usage()`
 * answers (a test moves it), a compaction that stands, and the prompts that
 * reach the bottom with the context the plugin attached.
 */
function engine(on: On, { env = {}, style = TO_HUMAN_STYLE }: { env?: Record<string, string>; style?: string } = {}) {
  mock.env(on, env)
  mock.store(on)
  mock.clock(on)
  const figure: { tokens: number | undefined } = { tokens: undefined }
  // How many of the next prompts a hook beneath refuses.
  const beneath = { drops: 0 }
  const entered: (readonly string[])[] = []
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('tool.register', (_, e, next) => ({ value: { tool: `mcp__${next.origin.plugin.replace(/[^a-zA-Z0-9_-]/g, '_')}__${e.name}` } }))
  on('config.list', () => ({
    value: [{ key: 'outputStyle', label: 'Output style', kind: 'choice', value: style, options: ['default'], provider: { plugin: 'engine', tier: 'core' }, isLocked: false }],
  }))
  on('session.usage', () => ({ value: { startedAt: 0, context: { tokens: figure.tokens, window: 1_000_000, percent: 0 }, rateLimits: [] } }) as never)
  on('session.compact', () => ({ messages: [{ role: 'user', text: 'The summary.', toolUses: [] }] }) as never)
  on('prompt.submit', (_, e) => (beneath.drops > 0 ? (beneath.drops--, { drop: 'refused beneath' }) : (entered.push(e.context ?? []), { text: e.text, context: e.context })) as never)
  on('ui.log', () => ({ value: undefined }))
  return { figure, entered, beneath }
}

const prompt = (text: string, extra: Record<string, unknown> = {}) => ({ text, origin: { kind: 'composer' }, wait: false, ...extra }) as never
const notification = prompt('<task-notification>done</task-notification>', { origin: { kind: 'task-notification' } })
const reminded = (entered: (readonly string[])[]) => entered.map((context) => context.includes(REMINDER))

describe('the reminder', () => {
  test('the points are the owner\'s: 150k, 300k and 450k tokens', () => {
    expect(REMIND_AT).toEqual([150_000, 300_000, 450_000])
    expect([undefined, 0, 149_999, 150_000, 299_999, 300_000, 450_000, 900_000].map(pointOf)).toEqual([0, 0, 0, 1, 1, 2, 3, 3])
    expect(REMINDER).toContain('mcp__to-human__message')
    expect(REMINDER).toContain('<message>')
  })

  test("a session's first prompt carries it, then the first prompt past each point, and no other", async ($, on) => {
    const { figure, entered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })

    await $.prompt.submit(prompt('start'))
    figure.tokens = 90_000
    await $.prompt.submit(notification)
    figure.tokens = 160_000
    await $.prompt.submit(notification)
    figure.tokens = 240_000
    await $.prompt.submit(prompt('next'))
    figure.tokens = 470_000
    await $.prompt.submit(notification)
    figure.tokens = 520_000
    await $.prompt.submit(notification)

    // Past 300k and 450k at once, the prompt carries it once.
    expect(reminded(entered)).toEqual([true, false, true, false, true, false])
    expect(entered[0]!.filter((context) => context === REMINDER)).toHaveLength(1)
  })

  test('a compaction re-arms the points, without a reminder of its own', async ($, on) => {
    const { figure, entered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(prompt('start'))
    figure.tokens = 200_000
    await $.prompt.submit(notification)

    await $.session.compact({ trigger: 'manual', messages: [{ role: 'user', text: 'start', toolUses: [] }] } as never)
    // Past 150k again with no lower figure read between: only the event re-armed it.
    figure.tokens = 155_000
    await $.prompt.submit(notification)

    expect(reminded(entered)).toEqual([true, true, true])
  })

  test('a context that fell back below a point without the event re-arms it too', async ($, on) => {
    const { figure, entered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(prompt('start'))
    figure.tokens = 200_000
    await $.prompt.submit(notification)
    figure.tokens = 30_000
    await $.prompt.submit(notification)
    figure.tokens = 151_000
    await $.prompt.submit(notification)

    expect(reminded(entered)).toEqual([true, true, false, true])
  })

  test('a module that starts mid-session (a reload) takes the point the context stands at and reminds nothing then', async ($, on) => {
    const { figure, entered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    figure.tokens = 210_000
    await $.prompt.submit(notification)
    figure.tokens = 290_000
    await $.prompt.submit(notification)
    figure.tokens = 310_000
    await $.prompt.submit(notification)

    expect(reminded(entered)).toEqual([false, false, true])
  })

  test('a slash command carries none; the next prompt does', async ($, on) => {
    const { entered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(prompt('/review', { command: { name: 'review', args: '', kind: 'prompt' } }))
    await $.prompt.submit(prompt('start'))

    expect(reminded(entered)).toEqual([false, true])
  })

  test('a prompt dropped beneath gives the reminder to the next one', async ($, on) => {
    const { entered, beneath } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    beneath.drops = 1
    await $.prompt.submit(prompt('refused'))
    await $.prompt.submit(prompt('start'))

    expect(reminded(entered)).toEqual([true])
  })

  test('where the message tool is not registered (MAWS, another style) nothing is attached', async ($, on) => {
    const maws = engine(on, { env: { MAWS_NATIVE_TO_HUMAN: '1' } })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(prompt('start'))

    expect(reminded(maws.entered)).toEqual([false])
  })

  test('under another output style nothing is attached', async ($, on) => {
    const other = engine(on, { style: 'default' })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(prompt('start'))

    expect(reminded(other.entered)).toEqual([false])
  })
})
