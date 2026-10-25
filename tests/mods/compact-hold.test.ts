import { describe, expect, test, tier } from 'claude-code/testing'
import type { On } from 'claude-code'

import { COMPACT, HOLD_SPARE_MS } from '../../hooks/mods/compact'

tier('user')

// The runtime's timer; the mods' declarations carry no host globals.
declare function setTimeout(fn: (value?: unknown) => void, ms: number): unknown

/**
 * The hold on a prompt typed over a turn that called compact, through the
 * engine's own hook dispatcher, whose budget a direct call of the handler
 * does not meter (HookBudget.ms): the plugin's hooks above, the test's
 * beneath, answering what the engine would.
 */
describe('the hold, under the hook budget', () => {
  const beneath = (on: On, passed: { at?: number }) => {
    on('prompt.submit', (_, e) => ((passed.at = Date.now()), { text: e.text }))
    on('turn.complete', () => ({ text: '' }) as never)
    on('clock.after', async (_, e) => {
      await new Promise((resolve) => setTimeout(resolve, (e as { ms: number }).ms))
      return { value: undefined } as never
    })
  }
  const typed = { text: 'and keep the ids', origin: { kind: 'composer' }, turnId: 't', wait: false } as never

  test("a prompt typed over the turn passes once the turn's end is in", { timeoutMs: 20_000 }, async ($, on) => {
    const passed: { at?: number } = {}
    beneath(on, passed)
    await $.tool.call({ tool: COMPACT, tool_use_id: 't1' } as never)
    const submitted = $.prompt.submit(typed)
    await new Promise((resolve) => setTimeout(resolve, 1_000))
    expect(passed.at).toBeUndefined()
    const ended = Date.now()
    await $.turn.complete({ turnId: 't', answer: '', durationMs: 1, isAborted: true, reason: 'aborted' } as never)
    await submitted
    expect(passed.at! - ended).toBeLessThan(1_000)
  })

  test('a prompt held to its budget passes before the budget runs out, not after', { timeoutMs: 20_000 }, async ($, on) => {
    const passed: { at?: number } = {}
    beneath(on, passed)
    await $.tool.call({ tool: COMPACT, tool_use_id: 't1' } as never)
    const sent = Date.now()
    await $.prompt.submit(typed)
    // The engine's budget is 10 s; past it the hook would be gone and its prompt passed on anyway.
    expect(passed.at! - sent).toBeGreaterThan(10_000 - HOLD_SPARE_MS - 1_500)
    expect(passed.at! - sent).toBeLessThan(10_000)
  })
})
