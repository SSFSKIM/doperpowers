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

  test('a notification that fails leaves the row stored', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    const session = mock.session(on)
    const clock = mock.clock(on)
    on('ui.notify', () => ({ deny: 'no channel here' }))

    const stored = await $.session.append(response('<message>Done.</message>'))
    await clock.settle()

    expect(stored.deny).toBeUndefined()
    expect(session.appended().length).toBe(1)
  })
})

describe('previewOf', () => {
  const text = (t: string) => [{ type: 'text', text: t }]

  test('reads the first message that says something, as one line without markup', () => {
    const critical = '<message>\n`⚠ Critical ────────`\nThe **build** broke in [the runner](/abs/ci.sh#L4).\n`──────`\n</message>'
    expect(previewOf(text(critical))).toBe('⚠ Critical The build broke in the runner.')
    expect(previewOf([{ type: 'tool_use' }, ...text('<message> </message><message>Next.</message>')])).toBe('Next.')
    expect(previewOf(text('No marks.'))).toBeUndefined()
  })

  test('cuts a long message to the banner\'s length', () => {
    const preview = previewOf(text(`<message>${'word '.repeat(100)}</message>`))!
    expect(preview.length).toBe(200)
    expect(preview.endsWith('…')).toBe(true)
  })
})
