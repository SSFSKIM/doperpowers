import { describe, expect, test, tier } from 'claude-code/testing'
import type { ClassicResultOf, EngineInterface } from 'claude-code'

import { NAME_DUE_TIMEOUT_MS, applyPendingName, renamedContext, resetName } from '../../hooks/mods/name'

tier('user')

const SESSION = '1a000001-0000-4000-8000-000000000001'
const PENDING = `{"session": "${SESSION}", "name": "desk-uplink-owner", "from": "work-0b", "line": "Owns the desk's uplink.", "ts": "2026-10-20T10:00:00Z"}`
const CONTEXT = 'sminos renamed this session to "desk-uplink-owner" after its standing responsibility; other sessions now see and address it by that name.'

type Result = ClassicResultOf['classic.UserPromptSubmit']
type Answer = { exitCode: number; stdout: string } | Error

/**
 * An engine of plain records: files by path, the CLI's answers in turn, the
 * env as set here. Every read and every run is logged.
 */
function harness(options: { files?: Record<string, string>; answers?: Answer[]; env?: Record<string, string> } = {}) {
  const files: Record<string, string> = { ...(options.files ?? {}) }
  const reads: string[] = []
  const runs: Array<{ argv: string[]; timeoutMs?: number }> = []
  const answers = [...(options.answers ?? [{ exitCode: 0, stdout: 'desk-uplink-owner\n' }])]
  const env = options.env ?? { HOME: '/home/u' }
  const $ = {
    plugin: { root: '/plugin' },
    env: { get: async (name: string) => env[name] },
    fs: {
      read: async (path: string) => {
        reads.push(path)
        const text = files[path]
        if (text === undefined) {
          throw new Error(`ENOENT: ${path}`)
        }
        return text
      },
    },
    process: {
      run: async (argv: string[], init?: { timeoutMs?: number }) => {
        runs.push({ argv, timeoutMs: init?.timeoutMs })
        const a = answers.length > 1 ? answers.shift() : answers[0]
        if (a instanceof Error) {
          throw a
        }
        return { exitCode: a?.exitCode ?? 0, stdout: a?.stdout ?? '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
      },
    },
  }
  resetName()
  const engine = $ as unknown as EngineInterface
  const prompt = (beneath: Result = {}, source?: string) =>
    applyPendingName(
      engine,
      { hook_event_name: 'UserPromptSubmit', session_id: SESSION, transcript_path: '/t.jsonl', cwd: '/w', prompt: 'hi', ...(source ? { source } : {}) } as never,
      async () => beneath,
    )
  return { files, reads, runs, prompt }
}

const FILE = `/home/u/.claude/sminos/names/${SESSION}.json`

describe('applyPendingName', () => {
  test('a due name: the session title and one line of context, the CLI asked once', async () => {
    const h = harness({ files: { [FILE]: PENDING } })
    expect(await h.prompt()).toEqual({ sessionTitle: 'desk-uplink-owner', additionalContext: [CONTEXT] })
    expect(h.runs).toEqual([{ argv: ['/plugin/skills/sminos/scripts/sminos', 'name-due', '--session', SESSION], timeoutMs: NAME_DUE_TIMEOUT_MS }])
  })

  test('the context beneath is kept, the line added after it', async () => {
    const h = harness({ files: { [FILE]: PENDING } })
    expect(await h.prompt({ additionalContext: ['from below'] })).toEqual({ sessionTitle: 'desk-uplink-owner', additionalContext: ['from below', CONTEXT] })
  })

  test('the same pending file at a second prompt runs no second check', async () => {
    const h = harness({ files: { [FILE]: PENDING } })
    await h.prompt()
    expect(await h.prompt()).toEqual({})
    expect(h.runs.length).toBe(1)
    expect(h.reads.length).toBe(2)
  })

  test('a name that is not due: the result unchanged, and not asked again for the same file', async () => {
    const h = harness({ files: { [FILE]: PENDING }, answers: [{ exitCode: 0, stdout: '' }] })
    expect(await h.prompt({ additionalContext: ['x'] })).toEqual({ additionalContext: ['x'] })
    expect(await h.prompt()).toEqual({})
    expect(h.runs.length).toBe(1)
  })

  test('a new pending file is checked afresh', async () => {
    const h = harness({ files: { [FILE]: PENDING }, answers: [{ exitCode: 0, stdout: '' }, { exitCode: 0, stdout: 'desk-uplink-keeper\n' }] })
    expect(await h.prompt()).toEqual({})
    h.files[FILE] = PENDING.replace('desk-uplink-owner', 'desk-uplink-keeper')
    expect((await h.prompt()).sessionTitle).toBe('desk-uplink-keeper')
    expect(h.runs.length).toBe(2)
  })

  test('no pending file: the CLI is never run', async () => {
    const h = harness()
    expect(await h.prompt({ additionalContext: ['x'] })).toEqual({ additionalContext: ['x'] })
    expect(h.reads).toEqual([FILE])
    expect(h.runs).toEqual([])
  })

  test('a CLI that cannot run leaves the file to the next prompt', async () => {
    const h = harness({ files: { [FILE]: PENDING }, answers: [new Error('timed out'), { exitCode: 0, stdout: 'desk-uplink-owner\n' }] })
    expect(await h.prompt()).toEqual({})
    expect((await h.prompt()).sessionTitle).toBe('desk-uplink-owner')
    expect(h.runs.length).toBe(2)
  })

  test('a CLI that answers with an error applies nothing, and is not asked again for the same file', async () => {
    const h = harness({ files: { [FILE]: PENDING }, answers: [{ exitCode: 2, stdout: 'desk-uplink-owner\n' }] })
    expect(await h.prompt()).toEqual({})
    expect(await h.prompt()).toEqual({})
    expect(h.runs.length).toBe(1)
  })

  test('a title set beneath passes unchanged, nothing read', async () => {
    const h = harness({ files: { [FILE]: PENDING } })
    expect(await h.prompt({ sessionTitle: 'theirs' })).toEqual({ sessionTitle: 'theirs' })
    expect(h.reads).toEqual([])
    expect(h.runs).toEqual([])
  })

  test('an internal fork reads nothing', async () => {
    const h = harness({ files: { [FILE]: PENDING }, env: { HOME: '/home/u', SMNS_INTERNAL: '1' } })
    expect(await h.prompt()).toEqual({})
    expect(h.reads).toEqual([])
    expect(h.runs).toEqual([])
  })

  test("the poll-event channel's enqueue-time pass is left to the prompt's own submit", async () => {
    const h = harness({ files: { [FILE]: PENDING } })
    expect(await h.prompt({}, 'poll_event')).toEqual({})
    expect(h.reads).toEqual([])
    expect((await h.prompt({}, 'system')).sessionTitle).toBe('desk-uplink-owner')
  })

  test("the pending file is under the CLI's own home: SMINOS_HOME, else DAEMON_HOME, else ~/.claude/sminos", async () => {
    const a = harness({ env: { HOME: '/home/u', SMINOS_HOME: '/s', DAEMON_HOME: '/d' } })
    await a.prompt()
    const b = harness({ env: { HOME: '/home/u', SMINOS_HOME: '', DAEMON_HOME: '/d' } })
    await b.prompt()
    const c = harness({ env: { HOME: '/home/u' } })
    await c.prompt()
    expect([a.reads, b.reads, c.reads]).toEqual([[`/s/names/${SESSION}.json`], [`/d/names/${SESSION}.json`], [FILE]])
  })
})

describe('renamedContext', () => {
  test('is the one line the model reads', async () => {
    expect(renamedContext('desk-uplink-owner')).toBe(CONTEXT)
  })
})
