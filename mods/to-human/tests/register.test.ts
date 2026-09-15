import { describe, expect, test, tier } from 'claude-code/testing'

import { parse } from '../hooks/register'

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

  test('parse finds no spans in an unmarked message', async () => {
    const parsed = parse('Plain reply.')

    expect(parsed.spans).toEqual([])
    expect(parsed.hasRecord).toBe(true)
  })
})
