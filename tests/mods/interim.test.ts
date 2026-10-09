import { describe, expect, test, tier } from 'claude-code/testing'
import type { On } from 'claude-code'

import { isInterim, registerInterim } from '../../hooks/mods/interim'

tier('user')

// The two notes the engine writes into an agent's completion notification
// (2.1.292), the interim one first.
const notification = (note: string) => `<task-notification>
<task-id>a6f9399af416f127b</task-id>
<status>completed</status>
<summary>Agent "Execute C10 sessions plan" finished</summary>
<note>${note}</note>
<result>report</result>
</task-notification>`
const INTERIM = notification('This agent stopped with background work of its own still running. It may resume on its own when that work completes or reports, and the same task-id notifies again if it does; the result below may be interim.')
const FINAL = notification('A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.')

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
