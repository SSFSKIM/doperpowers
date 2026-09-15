import { describe, expect, test, tier } from 'claude-code/testing'

import { readToggle } from '../hooks/register'

tier('user')

describe('readToggle', () => {
  test('reads the command under both of its names', async () => {
    expect(readToggle('kairos', '')).toBe(true)
    expect(readToggle('doperpowers:kairos', '')).toBe(true)
  })

  test('reads off, stop and end as off', async () => {
    expect(readToggle('kairos', 'off')).toBe(false)
    expect(readToggle('kairos', ' stop ')).toBe(false)
    expect(readToggle('doperpowers:kairos', 'end')).toBe(false)
  })

  test('ignores every other command', async () => {
    expect(readToggle('compact', '')).toBe(null)
    expect(readToggle('kairos-like', '')).toBe(null)
  })
})
