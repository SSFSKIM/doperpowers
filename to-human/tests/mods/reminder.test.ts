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
  // How many of the next prompts a hook beneath refuses; and, by its text, a
  // prompt held beneath (`hold`).
  const beneath = { drops: 0, held: new Map<string, { arrive: () => void; verdict: Promise<'refuse' | 'pass'> }>() }
  const entered: (readonly string[])[] = []
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('tool.register', (_, e, next) => ({ value: { tool: `mcp__${next.origin.plugin.replace(/[^a-zA-Z0-9_-]/g, '_')}__${e.name}` } }))
  on('config.list', () => ({
    value: [{ key: 'outputStyle', label: 'Output style', kind: 'choice', value: style, options: ['default'], provider: { plugin: 'engine', tier: 'core' }, isLocked: false }],
  }))
  on('session.usage', () => ({ value: { startedAt: 0, context: { tokens: figure.tokens, window: 1_000_000, percent: 0 }, rateLimits: [] } }) as never)
  on('session.compact', () => ({ messages: [{ role: 'user', text: 'The summary.', toolUses: [] }] }) as never)
  on('prompt.submit', async (_, e) => {
    const held = beneath.held.get(e.text)
    held?.arrive()
    const isRefused = held !== undefined ? (await held.verdict) === 'refuse' : beneath.drops > 0 ? (beneath.drops--, true) : false
    if (isRefused) {
      return { drop: 'refused beneath' } as never
    }
    entered.push(e.context ?? [])
    return { text: e.text, context: e.context } as never
  })
  on('ui.log', () => ({ value: undefined }))
  /**
   * Holds the prompt of this text beneath: `arrived` resolves once it is
   * there, and it waits until `open` refuses it or lets it pass.
   */
  const hold = (text: string) => {
    let arrive!: () => void
    let open!: (verdict: 'refuse' | 'pass') => void
    const arrived = new Promise<void>((resolve) => (arrive = resolve))
    beneath.held.set(text, { arrive, verdict: new Promise((resolve) => (open = resolve)) })
    return { arrived, open }
  }
  return { figure, entered, beneath, hold }
}

const prompt = (text: string, extra: Record<string, unknown> = {}) => ({ text, origin: { kind: 'composer' }, wait: false, ...extra }) as never
const command = (name: string) => prompt(`/${name}`, { command: { name, args: '', kind: 'prompt' } })
const notification = prompt('<task-notification>done</task-notification>', { origin: { kind: 'task-notification' } })
const reminded = (entered: (readonly string[])[]) => entered.map((context) => context.includes(REMINDER))

describe('the reminder', () => {
  test('the points are the owner\'s: 150k, 300k and 450k tokens', () => {
    expect(REMIND_AT).toEqual([150_000, 300_000, 450_000])
    expect([undefined, 0, 149_999, 150_000, 299_999, 300_000, 450_000, 900_000].map(pointOf)).toEqual([0, 0, 0, 1, 1, 2, 3, 3])
    expect(REMINDER).toContain('mcp__to-human__message')
    expect(REMINDER).toContain('<message>')
  })

  test("a fresh session's first prompt carries nothing, since the style stands just before it", async ($, on) => {
    const { entered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(prompt('start'))

    expect(reminded(entered)).toEqual([false])
  })

  test('the first prompt past each point carries it, and no other', async ($, on) => {
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

    expect(reminded(entered)).toEqual([false, false, true, false, true, false])
    // Past 300k and 450k at once, the prompt carries it once.
    expect(entered[4]!.filter((context) => context === REMINDER)).toHaveLength(1)
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

    expect(reminded(entered)).toEqual([false, true, true])
  })

  test('a context that fell back below a point without the event (a /clear) re-arms it too', async ($, on) => {
    const { figure, entered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(prompt('start'))
    figure.tokens = 200_000
    await $.prompt.submit(notification)
    figure.tokens = 30_000
    await $.prompt.submit(notification)
    figure.tokens = 151_000
    await $.prompt.submit(notification)

    expect(reminded(entered)).toEqual([false, true, false, true])
  })

  test('a module that starts mid-session (a reload, a resume) takes the point the context stands at and reminds nothing then', async ($, on) => {
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

  test("a slash command carries none, though the first one is where the module takes its point; the next prompt does", async ($, on) => {
    const { figure, entered } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(command('review'))
    figure.tokens = 160_000
    await $.prompt.submit(command('review'))
    await $.prompt.submit(prompt('next'))

    expect(reminded(entered)).toEqual([false, false, true])
  })

  test('a prompt dropped beneath gives the reminder to the next one', async ($, on) => {
    const { figure, entered, beneath } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(prompt('start'))
    figure.tokens = 160_000
    beneath.drops = 1
    await $.prompt.submit(prompt('refused'))
    await $.prompt.submit(prompt('next'))

    expect(reminded(entered)).toEqual([false, true])
  })

  test('a prompt dropped while a newer one passed without the reminder gives it to the next', async ($, on) => {
    const { figure, entered, hold } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    figure.tokens = 20_000
    await $.prompt.submit(prompt('start'))

    figure.tokens = 160_000
    const { arrived, open } = hold('screened')
    const screened = $.prompt.submit(prompt('screened'))
    await arrived
    await $.prompt.submit(prompt('typed'))
    open('refuse')
    await screened
    await $.prompt.submit(prompt('next'))

    expect(reminded(entered)).toEqual([false, false, true])
  })

  test("a prompt dropped after a newer one carried the next point's reminder does not undo it", async ($, on) => {
    const { figure, entered, hold } = engine(on)
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    figure.tokens = 20_000
    await $.prompt.submit(prompt('start'))

    figure.tokens = 160_000
    const { arrived, open } = hold('screened')
    const screened = $.prompt.submit(prompt('screened'))
    await arrived
    // While the earlier prompt is screened beneath, a newer one passes 300k and carries it.
    figure.tokens = 310_000
    await $.prompt.submit(prompt('typed'))
    open('refuse')
    expect((await screened).drop).toBe('refused beneath')
    await $.prompt.submit(prompt('next'))

    expect(reminded(entered)).toEqual([false, true, false])
  })

  test('where the message tool is not registered (MAWS, another style) nothing is attached', async ($, on) => {
    const maws = engine(on, { env: { MAWS_NATIVE_TO_HUMAN: '1' } })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(prompt('start'))
    maws.figure.tokens = 160_000
    await $.prompt.submit(prompt('next'))

    expect(reminded(maws.entered)).toEqual([false, false])
  })

  test('under another output style nothing is attached', async ($, on) => {
    const other = engine(on, { style: 'default' })
    await $.session.start({ cwd: '/w', surface: null, isInteractive: true })
    await $.prompt.submit(prompt('start'))
    other.figure.tokens = 160_000
    await $.prompt.submit(prompt('next'))

    expect(reminded(other.entered)).toEqual([false, false])
  })
})
