import { describe, expect, test, tier } from 'claude-code/testing'

import { MANAGED_OFF_LINE } from '../../hooks/mods/bridge-place'
import { call, isResultPosted, personsDevcloud, startBridge } from './bridge-seat-kit'

// The kit's `append` stands for the organization's: sminos here is seated by
// the managed settings, inside every plugin a person installs.
tier('append')

const POLICY = { appendPlugins: ['sminos@doperpowers'] }

describe('the bridge the organization seats in append: inside every plugin a person installs', () => {
  test("a person's devcloud outside it, its marker hidden from the bridge: the bridge turns off, naming the managed settings' prependPlugins", { plugins: [personsDevcloud] }, async ($, on) => {
    const { said, posted } = await startBridge($, on, { policy: POLICY, user: { enabledPlugins: { 'devcloud@doperpowers': true } } })
    await call($)
    // Judged, not left undecided: no read of its place failed.
    expect(said.filter((s) => s.includes('cannot check its place'))).toEqual([])
    expect(isResultPosted(posted)).toBe(false)
    expect(said.filter((s) => s.startsWith('devcloud heard'))).toEqual([])
    expect(said.filter((s) => s === MANAGED_OFF_LINE)).toHaveLength(2)
  })
})
