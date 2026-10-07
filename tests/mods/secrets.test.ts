import { describe, expect, mock, test, tier } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import { MASK, maskEcho, maskEdit } from '../../hooks/mods/secrets'

tier('user')

const type = (keys: string) => {
  let box = { text: '', cursor: 0 }
  let held = ''
  for (const key of keys) {
    const edit =
      key === '\b'
        ? { text: box.text, start: box.cursor - 1, end: box.cursor, inputText: '' }
        : { text: box.text, start: box.cursor, end: box.cursor, inputText: key }
    const masked = maskEdit(held, edit)
    held = masked.held
    box = masked.box ?? {
      text: edit.text.slice(0, edit.start) + edit.inputText + edit.text.slice(edit.end),
      cursor: edit.start + edit.inputText.length,
    }
  }
  return { box, held }
}

describe('the prompt box', () => {
  test('shows bullets for the value and holds the characters', () => {
    const { box, held } = type('/secret API_KEY sk-abc')
    expect(box.text).toBe(`/secret API_KEY ${MASK.repeat(6)}`)
    expect(held).toBe('sk-abc')
  })

  test('KEY=value is masked as KEY value is', () => {
    const { box, held } = type('/secret API_KEY=sk-abc')
    expect(box.text).toBe(`/secret API_KEY=${MASK.repeat(6)}`)
    expect(held).toBe('sk-abc')
  })

  test('backspace removes a held character', () => {
    const { box, held } = type('/secret API_KEY sk-abc\b\b')
    expect(box.text).toBe(`/secret API_KEY ${MASK.repeat(4)}`)
    expect(held).toBe('sk-a')
  })

  test('a pasted line is masked whole', () => {
    const masked = maskEdit('', { text: '', start: 0, end: 0, inputText: '/secret TOKEN hunter2 pass' })
    expect(masked.box?.text).toBe(`/secret TOKEN ${MASK.repeat(12)}`)
    expect(masked.held).toBe('hunter2 pass')
  })

  test('editing the key drops the value rather than showing any of it', () => {
    const text = `/secret TOKEN ${MASK.repeat(7)}`
    // Backspace over the space between key and value.
    const masked = maskEdit('a b c d', { text, start: 13, end: 14, inputText: '' })
    expect(masked.held).toBe('')
    expect(masked.box?.text).toBe('/secret TOKEN')
  })

  test('any other draft is left to the editor', () => {
    expect(maskEdit('', { text: 'hello', start: 5, end: 5, inputText: '!' }).box).toBeUndefined()
  })
})

test('an unmasked /secret echo is masked before the model reads it', () => {
  const echo = '<command-name>/secret</command-name>\n<command-args>API_KEY=sk-raw-1234</command-args>'
  expect(maskEcho(echo)).toBe(`<command-name>/secret</command-name>\n<command-args>API_KEY=${MASK.repeat(11)}</command-args>`)
  expect(maskEcho('<command-name>/other</command-name><command-args>A b</command-args>')).toContain('A b')
})

// A headless session whose Keychain holds `keychain`: the mod reads it at
// session start, as it does in a session (KAIROS keeps kairos off the disk).
const startWith = async ($: Engine, on: On, keychain: Record<string, string>) => {
  mock.env(on, { KAIROS: '1' })
  mock.store(on, { 'secrets.keys': Object.keys(keychain) })
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('process.run', (_, e) => {
    const value = keychain[e.argv[e.argv.indexOf('-a') + 1] ?? '']
    const ran = { stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
    return { value: value === undefined ? { ...ran, exitCode: 44, stdout: '' } : { ...ran, exitCode: 0, stdout: `${value}\n` } }
  })
  await $.session.start({ cwd: '/tmp', surface: null, isInteractive: false })
}

test('a stored value is scrubbed from a tool result the model would read', async ($, on) => {
  // Nothing beneath keeps a row in a test, so the append itself fails: this
  // hook records what reached the bottom on its way there.
  let kept: unknown
  on('session.append', (_, e, next) => {
    kept = e.message.content[0]?.content
    return next(e)
  })
  await startWith($, on, { API_KEY: 'sk-live-0123456789' })
  await $.session
    .append({
      message: {
        type: 'user',
        role: 'user',
        content: [{ type: 'tool_result', tool_use_id: 't1', content: 'Authorization: Bearer sk-live-0123456789' }],
      },
      door: 'tool-result',
      origin: { kind: 'tool', tool: 'Bash' },
      uuid: 'row-1',
    })
    .catch(() => undefined)
  expect(kept).toBe('Authorization: Bearer [secret:API_KEY]')
})

test('a tool record carrying a stored value is recorded scrubbed', async ($, on) => {
  on('tool.call', () => ({ result: { stdout: 'key=sk-live-0123456789', stderr: '', interrupted: false } }))
  await startWith($, on, { API_KEY: 'sk-live-0123456789' })
  const ran = await $.tool.call({ tool: 'Bash', command: 'env' })
  expect(ran.result).toEqual({ stdout: 'key=[secret:API_KEY]', stderr: '', interrupted: false })
})

test('a value typed in the clear is not stored', async ($) => {
  const ran = await $.command.run({
    command: 'secret',
    args: 'API_KEY sk-in-the-clear',
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 80 },
  })
  expect(ran.text).toContain('Not stored')
})
