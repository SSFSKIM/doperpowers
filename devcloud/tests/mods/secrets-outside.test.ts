import { describe, expect, test, tier } from 'claude-code/testing'

import { beneathSecondGuard, devcloudAloneScrubs, markerReader, secondGuard, start, tool, bash } from './secrets-kit'

// devcloud in `append`, so the kit seats a user-tier inline plugin outside it:
// a person's second guard outside devcloud's, the order secrets.test.ts
// (devcloud in `user`) cannot give.
tier('append')

describe("Interfaces I9 with a person's second guard outside devcloud's", () => {
  test("a person's plugin outside devcloud reads the loaded module's answer", { plugins: [markerReader('user')] }, async ($, on) => {
    tool(on, () => bash(''))
    await start($, on, {})
    expect((await $.tool.call({ tool: 'Bash', command: 'true' })).result).toEqual({ value: { owner: 'devcloud', version: 1 }, version: 0 })
  })

  test('a second guard outside devcloud passes every event on, and devcloud alone scrubs', { plugins: [secondGuard] }, async ($, on) => {
    await devcloudAloneScrubs($, on)
    expect(await beneathSecondGuard($)).toContain('append:devcloud')
  })
})
