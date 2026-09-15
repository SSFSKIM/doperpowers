import { describe, expect, test, tier } from 'claude-code/testing'

import { parse } from '../../hooks/mods/to-human'

tier('user')

describe('register', () => {
  test('parse splits marked spans from the working record', async () => {
    const parsed = parse(
      'Reading the file.\n<to-human>Done.</to-human>\n<essential>Tests fail.</essential>',
    )

    expect(parsed.spans).toEqual([
      { kind: 'to-human', text: 'Done.', isOpen: false },
      { kind: 'essential', text: 'Tests fail.', isOpen: false },
    ])
    expect(parsed.hasRecord).toBe(true)
  })

  test('parse leaves an unclosed span open while it streams', async () => {
    const parsed = parse('<need-input>Which branch')

    expect(parsed.spans).toEqual([{ kind: 'need-input', text: 'Which branch', isOpen: true }])
    expect(parsed.hasRecord).toBe(false)
  })

  test('parse lifts a mark nested inside another into a span of its own', async () => {
    const parsed = parse(
      '<to-human>\nDone.\n\n<essential>\nTests fail.\n</essential>\nMore.\n</to-human>',
    )

    expect(parsed.spans).toEqual([
      { kind: 'to-human', text: 'Done.', isOpen: false },
      { kind: 'essential', text: 'Tests fail.', isOpen: false },
      { kind: 'to-human', text: 'More.', isOpen: false },
    ])
    expect(parsed.hasRecord).toBe(false)
  })

  test('parse does not let an unclosed mark swallow the marks after it', async () => {
    const parsed = parse('<to-human>Done.\n<essential>Tests fail.</essential>\n<need-input>Which')

    expect(parsed.spans).toEqual([
      { kind: 'to-human', text: 'Done.', isOpen: false },
      { kind: 'essential', text: 'Tests fail.', isOpen: false },
      { kind: 'need-input', text: 'Which', isOpen: true },
    ])
  })

  test('parse finds no spans in an unmarked message', async () => {
    const parsed = parse('Plain reply.')

    expect(parsed.spans).toEqual([])
    expect(parsed.hasRecord).toBe(true)
  })
})
