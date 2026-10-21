import { describe, expect, test, tier } from 'claude-code/testing'
import type { AttributionTextInput, EngineInterface, On } from 'claude-code'

import { ADDRESS_RETRY_MS, ADDRESS_TTL_MS, addressText, registerAddress, resetAddress, withAddress } from '../../hooks/mods/address'

tier('user')

const LINE = 'Sminos-Session: fixer#1a000001 (teamproj on alpha)'

describe('withAddress', () => {
  test('an empty composed text becomes the line alone', async () => {
    expect(withAddress('commit', '', LINE)).toBe(LINE)
    expect(withAddress('pr', '', LINE)).toBe(LINE)
  })

  test("a commit's trailer joins the trailer block it ends in", async () => {
    expect(withAddress('commit', 'Co-Authored-By: C <c@x>', LINE)).toBe(`Co-Authored-By: C <c@x>\n${LINE}`)
    expect(withAddress('commit', 'Claude-Session: https://x/y\n', LINE)).toBe(`Claude-Session: https://x/y\n${LINE}`)
  })

  test("a commit's text that is no trailer gets the line as a paragraph of its own", async () => {
    expect(withAddress('commit', 'Made with a tool', LINE)).toBe(`Made with a tool\n\n${LINE}`)
  })

  test("a PR body's line is its last, after a blank line", async () => {
    expect(withAddress('pr', 'Generated with Claude Code', LINE)).toBe(`Generated with Claude Code\n\n${LINE}`)
  })

  test('no line, another kind, or a text that has the line: unchanged', async () => {
    expect(withAddress('commit', 'Co-Authored-By: C <c@x>', '')).toBe('Co-Authored-By: C <c@x>')
    expect(withAddress('exemption', 'some sentence', LINE)).toBe('some sentence')
    expect(withAddress('pr', `body\n\n${LINE}`, LINE)).toBe(`body\n\n${LINE}`)
  })
})

type Answer = { exitCode: number; stdout: string } | Error
type Handler = (...args: unknown[]) => Promise<unknown>

/**
 * An engine of plain records: the CLI's answers in turn (each held until
 * `answer()` when `held`), the session id and the env as set here; and the
 * mod's hooks as registered, for a compaction.
 */
function harness(options: { answers?: Answer[]; env?: Record<string, string>; held?: boolean } = {}) {
  const runs: string[][] = []
  const waiting: Array<() => void> = []
  const state = { session: '1a000001-0000-4000-8000-000000000001', clock: 1_000_000 }
  const answers = [...(options.answers ?? [{ exitCode: 0, stdout: `${LINE}\n` }])]
  const $ = {
    plugin: { root: '/plugin' },
    session: { id: async () => state.session },
    env: { get: async (name: string) => options.env?.[name] },
    process: {
      run: async (argv: string[]) => {
        runs.push(argv)
        if (options.held) {
          await new Promise<void>((resolve) => waiting.push(resolve))
        }
        const a = answers.length > 1 ? answers.shift() : answers[0]
        if (a instanceof Error) {
          throw a
        }
        return { exitCode: a?.exitCode ?? 0, stdout: a?.stdout ?? '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
      },
    },
  }
  const hooks: { event: string; matcher: Record<string, RegExp>; handler: Handler }[] = []
  const on = ((event: string, matcher: Record<string, RegExp>, handler: Handler) => {
    hooks.push({ event, matcher, handler })
    return { catch: () => undefined }
  }) as unknown as On
  resetAddress()
  registerAddress(on)
  const engine = $ as unknown as EngineInterface
  // Microtask turns, so an ask the hook let run in the background settles.
  const settle = async () => {
    for (let i = 0; i < 50; i++) {
      await Promise.resolve()
    }
  }
  const ask = (kind: AttributionTextInput['kind'], text = '') =>
    addressText(engine, { kind, text }, async (e) => ({ text: e.text }), () => state.clock).then((r) => r.text)
  /** A compaction by `trigger`, standing or skipped, through the hooks the engine would run for it. */
  const compact = async (trigger: string, result: { messages: [] } | { skip: string }) => {
    for (const h of hooks.filter((x) => x.event === 'session.compact' && x.matcher.trigger?.test(trigger))) {
      await h.handler(engine, { trigger, messages: [] }, async () => result)
    }
  }
  /** Lets every held CLI call answer (once a request in flight has reached its call), and what waits on it settle. */
  const answer = async () => {
    await settle()
    waiting.splice(0).forEach((resolve) => resolve())
    await settle()
  }
  return { runs, state, ask, compact, answer, settle }
}

describe('addressText', () => {
  test("adds the CLI's line, asked once for the commit and the PR of one request", async () => {
    const h = harness()
    expect(await h.ask('commit')).toBe(LINE)
    expect(await h.ask('pr', 'Generated')).toBe(`Generated\n\n${LINE}`)
    expect(h.runs).toEqual([['/plugin/skills/sminos/scripts/sminos', 'who', '--session', '1a000001-0000-4000-8000-000000000001']])
  })

  test('asks nothing while the line could not have changed, a minute on and up to its ten', async () => {
    const h = harness()
    expect(await h.ask('commit')).toBe(LINE)
    h.state.clock += 61_000
    expect(await h.ask('commit')).toBe(LINE)
    h.state.clock += 5 * 60_000
    expect(await h.ask('pr')).toBe(LINE)
    h.state.clock = 1_000_000 + ADDRESS_TTL_MS - 1
    expect(await h.ask('commit')).toBe(LINE)
    expect(h.runs.length).toBe(1)
  })

  test('a line come due is used at once while the CLI is asked in the background; the next request has its answer', async () => {
    const renamed = 'Sminos-Session: fixer2#1a000001 (teamproj on alpha)'
    const h = harness({ answers: [{ exitCode: 0, stdout: LINE }, { exitCode: 0, stdout: renamed }], held: true })
    const first = h.ask('commit')
    await h.answer()
    expect(await first).toBe(LINE)
    h.state.clock += ADDRESS_TTL_MS
    expect(await h.ask('commit')).toBe(LINE)
    expect(await h.ask('pr')).toBe(LINE)
    expect(h.runs.length).toBe(2)
    await h.answer()
    expect(await h.ask('commit')).toBe(renamed)
    expect(h.runs.length).toBe(2)
  })

  test('a new session id asks at once, and its request waits for the answer', async () => {
    const moved = 'Sminos-Session: fixer2#3c000003 (teamproj on alpha)'
    const h = harness({ answers: [{ exitCode: 0, stdout: LINE }, { exitCode: 0, stdout: moved }] })
    expect(await h.ask('commit')).toBe(LINE)
    h.state.clock += 1000
    h.state.session = '3c000003-0000-4000-8000-000000000003'
    expect(await h.ask('commit')).toBe(moved)
    expect(h.runs.map((r) => r[3])).toEqual(['1a000001-0000-4000-8000-000000000001', '3c000003-0000-4000-8000-000000000003'])
  })

  test('a compaction that stood asks again at the next request; a skipped one, or a precompute, does not', async () => {
    const renamed = 'Sminos-Session: fixer2#1a000001 (teamproj on alpha)'
    const h = harness({ answers: [{ exitCode: 0, stdout: LINE }, { exitCode: 0, stdout: renamed }] })
    expect(await h.ask('commit')).toBe(LINE)
    await h.compact('precompute', { messages: [] })
    await h.compact('auto', { skip: 'blocked' })
    expect(await h.ask('commit')).toBe(LINE)
    expect(h.runs.length).toBe(1)
    await h.compact('auto', { messages: [] })
    expect(await h.ask('commit')).toBe(LINE)
    expect(h.runs.length).toBe(2)
    await h.settle()
    expect(await h.ask('commit')).toBe(renamed)
    expect(h.runs.length).toBe(2)
  })

  test('a session with no address gets the composed text unchanged, and is asked again a minute on', async () => {
    const h = harness({ answers: [{ exitCode: 0, stdout: '' }, { exitCode: 0, stdout: LINE }] })
    expect(await h.ask('commit', 'Co-Authored-By: C <c@x>')).toBe('Co-Authored-By: C <c@x>')
    h.state.clock += ADDRESS_RETRY_MS - 1
    expect(await h.ask('commit')).toBe('')
    expect(h.runs.length).toBe(1)
    h.state.clock += 1
    expect(await h.ask('commit')).toBe('')
    await h.settle()
    expect(await h.ask('commit')).toBe(LINE)
    expect(h.runs.length).toBe(2)
  })

  test('a CLI that fails keeps the line it had and is asked again a minute on; a first failure adds nothing', async () => {
    const h = harness({ answers: [new Error('spawn failed'), { exitCode: 0, stdout: LINE }, { exitCode: 1, stdout: '' }, { exitCode: 0, stdout: LINE }] })
    expect(await h.ask('commit')).toBe('')
    h.state.clock += ADDRESS_RETRY_MS
    expect(await h.ask('commit')).toBe('')
    await h.settle()
    expect(await h.ask('commit')).toBe(LINE)
    h.state.clock += ADDRESS_TTL_MS
    expect(await h.ask('commit')).toBe(LINE)
    await h.settle()
    expect(h.runs.length).toBe(3)
    h.state.clock += ADDRESS_RETRY_MS - 1
    expect(await h.ask('commit')).toBe(LINE)
    expect(h.runs.length).toBe(3)
    h.state.clock += 1
    expect(await h.ask('commit')).toBe(LINE)
    expect(h.runs.length).toBe(4)
  })

  test('an internal fork is left alone and asks nothing', async () => {
    const h = harness({ env: { SMNS_INTERNAL: '1' } })
    expect(await h.ask('commit', 'x')).toBe('x')
    expect(h.runs).toEqual([])
  })
})
