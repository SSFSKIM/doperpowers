import type { SessionAppendInput } from 'claude-code'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import { previewOf } from '../../hooks/mods/notify'

tier('user')

const MODEL = { kind: 'model', model: 'claude-opus-5-5' } as const

const response = (text: string, agentId?: string): SessionAppendInput => ({
  message: { type: 'assistant', role: 'assistant', content: [{ type: 'text', text }] },
  door: 'response',
  origin: MODEL,
  uuid: `r-${text.length}`,
  ...(agentId !== undefined && { agentId }),
})

describe('a message notifies the person', () => {
  test('a main-conversation response that sends a message raises one notification of it', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    const clock = mock.clock(on)
    const notified: { text: string }[] = []
    on('ui.notify', (_, e) => (notified.push(e), { value: { isSent: true, channel: 'terminal_bell' } }))

    await $.session.append(response('Reading the logs.\n<message>The fix is in.</message>\n<message>Second.</message>'))
    await clock.settle()

    expect(notified.map((e) => e.text)).toEqual(['The fix is in.'])
  })

  test('working record, a quoted mark, a subagent\'s message and the person\'s prompt raise none', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    const clock = mock.clock(on)
    const notified: unknown[] = []
    on('ui.notify', (_, e) => (notified.push(e), { value: { isSent: true, channel: 'terminal_bell' } }))

    await $.session.append(response('Reading the logs.'))
    await $.session.append(response('The style asks for `<message>` spans.\n```\n<message>example</message>\n```'))
    await $.session.append(response('<message></message>'))
    await $.session.append(response('<message>Done.</message>', 'a1'))
    await $.session.append({
      message: { type: 'user', role: 'user', content: [{ type: 'text', text: '<message>quoted</message>' }] },
      door: 'prompt',
      origin: { kind: 'composer' },
      uuid: 'p1',
    })
    await clock.settle()

    expect(notified).toEqual([])
  })

  test('a MAWS session raises none: MAWS is its notification surface', async ($, on) => {
    mock.env(on, { MAWS_NATIVE_TO_HUMAN: '7' })
    mock.store(on)
    const clock = mock.clock(on)
    const notified: unknown[] = []
    on('ui.notify', (_, e) => (notified.push(e), { value: { isSent: true, channel: 'terminal_bell' } }))

    await $.session.append(response('<message>Done.</message>'))
    await clock.settle()

    expect(notified).toEqual([])
  })

  test('an internal fork of sminos raises none', async ($, on) => {
    mock.env(on, { SMNS_INTERNAL: '1' })
    mock.store(on)
    const clock = mock.clock(on)
    const notified: unknown[] = []
    on('ui.notify', (_, e) => (notified.push(e), { value: { isSent: true, channel: 'terminal_bell' } }))

    await $.session.append(response('<message>Done.</message>'))
    await clock.settle()

    expect(notified).toEqual([])
  })

  test('a notification that never settles does not hold the row', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    const session = mock.session(on)
    const clock = mock.clock(on)
    on('ui.notify', () => new Promise<never>(() => {}))

    const appended = $.session.append(response('<message>Done.</message>')).then(() => 'stored' as const)
    const held = clock.sleep(1000).then(() => 'held' as const)
    void clock.advance(1000)

    expect(await Promise.race([appended, held])).toBe('stored')
    expect(session.appended().length).toBe(1)
  })

  test('a notification that is refused ends in a debug line', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    const clock = mock.clock(on)
    const logged: { text: string; to: string }[] = []
    on('ui.log', (_, e) => (logged.push(e), { value: undefined }))
    on('ui.notify', () => ({ deny: 'no channel here' }))

    await $.session.append(response('<message>Done.</message>'))
    await clock.settle()

    expect(logged.map((e) => e.to)).toEqual(['debug'])
    expect(logged[0]!.text).toContain('notification failed')
  })
})

describe('previewOf', () => {
  const text = (t: string) => [{ type: 'text', text: t }]

  test('reads the first message that says something, as one line without markup', () => {
    const critical = '<message>\n> **⚠ Critical** The **build** broke in [the runner](/abs/ci.sh#L4).\n>\n> **Handled:** no.\n</message>'
    expect(previewOf(text(critical))).toBe('⚠ Critical The build broke in the runner. Handled: no.')
    const earlier = '<message>\n`⚠ Critical ────────`\nThe build broke.\n`──────`\n</message>'
    expect(previewOf(text(earlier))).toBe('⚠ Critical The build broke.')
    const asking = '<message>Done; *pick per key or per org*, since it sets what customers pay.</message>'
    expect(previewOf(text(asking))).toBe('Done; pick per key or per org, since it sets what customers pay.')
    expect(previewOf([{ type: 'tool_use' }, ...text('<message> </message><message>Next.</message>')])).toBe('Next.')
    expect(previewOf(text('No marks.'))).toBeUndefined()
  })

  test('takes a link target with parentheses whole', () => {
    expect(previewOf(text('<message>See [page](/abs/app/(auth)/page.tsx#L4) now.</message>'))).toBe('See page now.')
  })

  test('cuts a long message to the banner\'s length', () => {
    const preview = previewOf(text(`<message>${'word '.repeat(100)}</message>`))!
    expect(preview.length).toBe(200)
    expect(preview.endsWith('…')).toBe(true)
  })
})
