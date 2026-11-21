import { describe, expect, test, tier } from 'claude-code/testing'

import { call, isResultPosted, personsDevcloud, startBridge } from './bridge-seat-kit'

// A person's sminos, in `user`, as the engine loads every plugin a person
// enables on a machine with managed settings: its reads reach a person's
// devcloud, whatever the managed settings hold.
tier('user')

describe("a person's bridge, in user: devcloud's marker is heard", () => {
  test("a person's devcloud beneath it answers the bridge's read, and the bridge stays on", { plugins: [personsDevcloud] }, async ($, on) => {
    const { said, posted } = await startBridge($, on, { policy: { prependPlugins: ['to-human@doperpowers'] }, user: { enabledPlugins: { 'devcloud@doperpowers': true } } })
    await call($)
    // Judged, not left undecided: no read of its place failed.
    expect(said.filter((s) => s.includes('cannot check its place'))).toEqual([])
    expect(isResultPosted(posted)).toBe(true)
    expect(said.filter((s) => s.startsWith('devcloud heard'))).toEqual(['devcloud heard a read of its marker from sminos'])
    expect(said.filter((s) => s.includes('the bridge is off'))).toEqual([])
  })
})
