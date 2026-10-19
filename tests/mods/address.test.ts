import { describe, expect, test, tier } from 'claude-code/testing'
import type { AttributionTextInput, EngineInterface } from 'claude-code'

import { ADDRESS_TTL_MS, addressText, resetAddress, withAddress } from '../../hooks/mods/address'

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

/** An engine of plain records: the CLI's answers in turn, the session id and the env as set here. */
function harness(options: { answers?: Array<{ exitCode: number; stdout: string } | Error>; env?: Record<string, string> } = {}) {
  const runs: string[][] = []
  const state = { session: '1a000001-0000-4000-8000-000000000001', clock: 1_000_000 }
  const answers = [...(options.answers ?? [{ exitCode: 0, stdout: `${LINE}\n` }])]
  const $ = {
    plugin: { root: '/plugin' },
    session: { id: async () => state.session },
    env: { get: async (name: string) => options.env?.[name] },
    process: {
      run: async (argv: string[]) => {
        runs.push(argv)
        const a = answers.length > 1 ? answers.shift() : answers[0]
        if (a instanceof Error) {
          throw a
        }
        return { exitCode: a?.exitCode ?? 0, stdout: a?.stdout ?? '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
      },
    },
  }
  resetAddress()
  const engine = $ as unknown as EngineInterface
  const ask = (kind: AttributionTextInput['kind'], text = '') =>
    addressText(engine, { kind, text }, async (e) => ({ text: e.text }), () => state.clock).then((r) => r.text)
  return { runs, state, ask }
}

describe('addressText', () => {
  test('adds the CLI\'s line, asked once for the commit and the PR of one request', async () => {
    const h = harness()
    expect(await h.ask('commit')).toBe(LINE)
    expect(await h.ask('pr', 'Generated')).toBe(`Generated\n\n${LINE}`)
    expect(h.runs).toEqual([['/plugin/skills/sminos/scripts/sminos', 'who', '--session', '1a000001-0000-4000-8000-000000000001']])
  })

  test('asks again once the line is a minute old, and for a new session id at once', async () => {
    const renamed = 'Sminos-Session: fixer2#1a000001 (teamproj on alpha)'
    const moved = 'Sminos-Session: fixer2#3c000003 (teamproj on alpha)'
    const h = harness({ answers: [{ exitCode: 0, stdout: LINE }, { exitCode: 0, stdout: renamed }, { exitCode: 0, stdout: moved }] })
    expect(await h.ask('commit')).toBe(LINE)
    h.state.clock += ADDRESS_TTL_MS - 1
    expect(await h.ask('commit')).toBe(LINE)
    h.state.clock += 1
    expect(await h.ask('commit')).toBe(renamed)
    h.state.session = '3c000003-0000-4000-8000-000000000003'
    expect(await h.ask('commit')).toBe(moved)
    expect(h.runs.length).toBe(3)
  })

  test('a session with no address gets the composed text unchanged', async () => {
    const h = harness({ answers: [{ exitCode: 0, stdout: '' }] })
    expect(await h.ask('commit', 'Co-Authored-By: C <c@x>')).toBe('Co-Authored-By: C <c@x>')
  })

  test('a CLI that fails keeps the line it had, and a first failure adds nothing', async () => {
    const h = harness({ answers: [new Error('spawn failed'), { exitCode: 0, stdout: LINE }, { exitCode: 1, stdout: '' }] })
    expect(await h.ask('commit')).toBe('')
    h.state.clock += ADDRESS_TTL_MS
    expect(await h.ask('commit')).toBe(LINE)
    h.state.clock += ADDRESS_TTL_MS
    expect(await h.ask('commit')).toBe(LINE)
  })

  test('an internal fork is left alone and asks nothing', async () => {
    const h = harness({ env: { SMNS_INTERNAL: '1' } })
    expect(await h.ask('commit', 'x')).toBe('x')
    expect(h.runs).toEqual([])
  })
})
