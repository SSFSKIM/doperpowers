import { describe, expect, test, tier } from 'claude-code/testing'

import { OFF_LINE } from '../../hooks/mods/bridge-place'
import { call, isResultPosted, personsDevcloud, startBridge } from './bridge-seat-kit'

// The kit's `prepend` stands for the organization's: sminos here is seated by
// the managed settings, and a person's hooks do not hear its calls.
tier('prepend')

const POLICY = { prependPlugins: ['sminos@doperpowers'] }

describe("the bridge the organization seats in prepend: outside every plugin a person installs", () => {
  test("a person's devcloud beneath it, its marker hidden from the bridge, and cua enabled in the user settings but not loaded: the bridge stays on", { plugins: [personsDevcloud] }, async ($, on) => {
    const { said, posted } = await startBridge($, on, { policy: POLICY, user: { enabledPlugins: { 'devcloud@doperpowers': true, 'cua@cua': true } } })
    await call($)
    // Judged, not left undecided: no read of its place failed.
    expect(said.filter((s) => s.includes('cannot check its place'))).toEqual([])
    expect(isResultPosted(posted)).toBe(true)
    // The engine kept the bridge's read from the person's devcloud.
    expect(said.filter((s) => s.startsWith('devcloud heard'))).toEqual([])
    expect(said.filter((s) => s.includes('the bridge is off'))).toEqual([])
    expect(said).not.toContain(OFF_LINE)
  })
})
