import { describe, expect, test, tier } from 'claude-code/testing'
import type { On } from 'claude-code'

import { INTERIM_NOTE, isInterim, registerInterim } from '../../hooks/mods/interim'

tier('user')

// The two notes the engine writes into an agent's completion notification
// (2.1.292), the interim one first.
const WAITING = 'This agent has not reported yet: it is waiting on its own background work and will deliver its report through SubagentHandback when that finishes.'
const notification = (note: string, result = WAITING, status = 'completed') => `<task-notification>
<task-id>a6f9399af416f127b</task-id>
<status>${status}</status>
<summary>Agent "Execute C10 sessions plan" finished</summary>
<note>${note}</note>
<result>${result}
</result>
</task-notification>`
const INTERIM_TEXT = 'This agent stopped with background work of its own still running. It may resume on its own when that work completes or reports, and the same task-id notifies again if it does; the result below may be interim.'
const INTERIM = notification(INTERIM_TEXT)
const FINAL_NOTE = 'A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.'
const FINAL = notification(FINAL_NOTE)

type Hook = { event: string; matcher: unknown; handler: (...args: unknown[]) => Promise<unknown> }

function hooks(): Hook[] {
  const registered: Hook[] = []
  registerInterim(((event: string, matcher: unknown, handler: Hook['handler']) => {
    registered.push({ event, matcher, handler })
  }) as unknown as On)
  return registered
}

describe('isInterim', () => {
  test('reads the interim note and nothing else', async () => {
    expect(isInterim(INTERIM)).toBe(true)
    expect(isInterim(FINAL)).toBe(false)
  })

  test('reads a pointer to a delivered report as interim too', async () => {
    expect(isInterim(notification(INTERIM_TEXT, 'This agent\'s report was delivered to you as a message from "a1" (its SubagentHandback call). Read it there; it is not repeated here.'))).toBe(true)
  })

  test('passes an interim notification whose result is the agent\'s own text', async () => {
    expect(isInterim(notification(INTERIM_TEXT, '{"verdict":"incorrect","findings":[]}'))).toBe(false)
    expect(isInterim(notification(INTERIM_TEXT, ''))).toBe(false)
  })

  test('reads the security-warning pointer as interim too', async () => {
    expect(isInterim(notification(INTERIM_TEXT, 'This agent\'s report was delivered to you as a message from "a1" (its SubagentHandback call), under a SECURITY WARNING from auto mode \u2014 the warning above the report says why. Read it there; it is not repeated here.'))).toBe(true)
  })

  test('passes a result that carries anything beyond one placeholder', async () => {
    expect(isInterim(notification(INTERIM_TEXT, `${WAITING} Turn limit reached.`))).toBe(false)
    expect(isInterim(notification(INTERIM_TEXT, `${WAITING}\nAlso: the build is red.`))).toBe(false)
    expect(isInterim(notification(INTERIM_TEXT, 'The agent says: ' + WAITING))).toBe(false)
    expect(isInterim(notification(INTERIM_TEXT, 'This agent\'s report was delivered to you as a message from "a1" (its SubagentHandback call). Read it there; it is not repeated here. Warning: turn limit.'))).toBe(false)
  })

  test('passes a final note whose result or summary quotes the interim sentence', async () => {
    expect(isInterim(notification(FINAL_NOTE, `${INTERIM_TEXT}\n${WAITING}`))).toBe(false)
    expect(isInterim(notification(FINAL_NOTE).replace('finished</summary>', `finished: ${INTERIM_NOTE}</summary>`))).toBe(false)
  })

  test('passes a notification whose status is not completed', async () => {
    expect(isInterim(notification(INTERIM_TEXT, WAITING, 'failed'))).toBe(false)
    expect(isInterim(notification(INTERIM_TEXT, WAITING, 'killed'))).toBe(false)
  })

  test('reads only a notification, not a prompt quoting one', async () => {
    expect(isInterim(`why did this come in?\n${INTERIM}`)).toBe(false)
  })
})

describe('registerInterim', () => {
  test('hooks task notifications alone', async () => {
    const hook = hooks()[0]!
    expect(hook.event).toBe('prompt.submit')
    expect(hook.matcher).toEqual({ origin: { kind: 'task-notification' } })
  })

  test('drops an interim notification and passes the final one', async () => {
    const hook = hooks()[0]!
    const passed = Object.freeze({ text: FINAL })
    let called = 0
    const next = async () => (called++, passed)
    const dropped = await hook.handler({}, { text: INTERIM, origin: { kind: 'task-notification' } }, next) as { drop?: string }
    expect(typeof dropped.drop).toBe('string')
    expect(called).toBe(0)
    expect(await hook.handler({}, { text: FINAL, origin: { kind: 'task-notification' } }, next)).toBe(passed)
    expect(called).toBe(1)
  })
})
