import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface } from 'claude-code'

import { NAME_DUE_TIMEOUT_MS, POLL_MS, createNamer, resetName, sessionEnded, startNaming, turnEnded, turnStarted } from '../../hooks/mods/name'
import type { NameIo } from '../../hooks/mods/name'

tier('user')

const SESSION = '1a000001-0000-4000-8000-000000000001'
const PENDING = `{"session": "${SESSION}", "name": "desk-uplink-owner", "from": "work-0b", "line": "Owns the desk's uplink.", "ts": "2026-10-20T10:00:00Z"}`

type Answer = { exitCode: number; stdout: string } | Error

const OTHER = '1a000002-0000-4000-8000-000000000002'
const OTHER_PENDING = PENDING.replace(SESSION, OTHER).replace('desk-uplink-owner', 'desk-relay-keeper')

/**
 * The namer's world as plain records: the session the process is in, each
 * session's pending file, the CLI's answers in turn, the turn and the dialog
 * as set here. Every read, check and rename is logged. `during` runs while
 * the CLI answers, `onDialogRead` at each read of the dialog (with its count);
 * `gated` holds each check until `release()`.
 */
function world(
  options: { file?: string; answers?: Answer[]; during?: () => void; onDialogRead?: (n: number) => void; gated?: boolean; refuse?: boolean } = {},
) {
  const w = {
    session: SESSION,
    files: { ...(options.file !== undefined && { [SESSION]: options.file }) } as Record<string, string | undefined>,
    isDialogUp: false,
    dialogReads: 0,
    reads: [] as string[],
    checks: [] as string[],
    renames: [] as string[],
    renamedIn: [] as string[],
    logs: [] as string[],
    release: () => {},
  }
  const answers = [...(options.answers ?? [{ exitCode: 0, stdout: 'desk-uplink-owner\n' }])]
  const next = () => {
    const a = answers.length > 1 ? answers.shift() : answers[0]
    return a ?? { exitCode: 0, stdout: '' }
  }
  resetName()
  const io: NameIo = {
    session: async () => w.session,
    read: async (session) => {
      w.reads.push(session)
      const text = w.files[session]
      if (text === undefined) {
        throw new Error('ENOENT')
      }
      return text
    },
    due: (session) => {
      w.checks.push(session)
      options.during?.()
      const a = next()
      if (!options.gated) {
        return a instanceof Error ? Promise.reject(a) : Promise.resolve(a)
      }
      return new Promise((resolve, reject) => {
        w.release = () => (a instanceof Error ? reject(a) : resolve(a))
      })
    },
    rename: async (name) => {
      w.renames.push(name)
      w.renamedIn.push(w.session)
      if (options.refuse) {
        throw new Error('past a Stop')
      }
    },
    isAskDialogUp: async () => {
      w.dialogReads += 1
      options.onDialogRead?.(w.dialogReads)
      return w.isDialogUp
    },
    log: (line) => w.logs.push(line),
  }
  return { w, namer: createNamer(io) }
}

/** Lets every promise already started run to its end (none here waits on a clock). */
async function settle() {
  for (let i = 0; i < 50; i += 1) {
    await Promise.resolve()
  }
}

/** The first call of a callback only: a race that happens once. */
function once(fn: () => void) {
  let isDone = false
  return () => {
    if (!isDone) {
      isDone = true
      fn()
    }
  }
}

const MAIN = { turnId: 't1' } as never
const SUB = { turnId: 't2', agentId: 'a1' } as never

describe('createNamer', () => {
  test('an idle tick with a due name renames the session once; the same file at a later tick runs no second check', async () => {
    const { w, namer } = world({ file: PENDING })
    await namer.tick()
    expect(w.renames).toEqual(['desk-uplink-owner'])
    await namer.tick()
    await namer.tick()
    expect(w.checks).toEqual([SESSION])
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test('no pending file: the CLI is never run', async () => {
    const { w, namer } = world()
    await namer.tick()
    await namer.tick()
    expect(w.reads).toEqual([SESSION, SESSION])
    expect(w.checks).toEqual([])
    expect(w.renames).toEqual([])
  })

  test('a name that is not due renames nothing, and is not asked again for the same file', async () => {
    const { w, namer } = world({ file: PENDING, answers: [{ exitCode: 0, stdout: '' }] })
    await namer.tick()
    await namer.tick()
    expect(w.checks.length).toBe(1)
    expect(w.renames).toEqual([])
  })

  test('a new pending file is checked afresh', async () => {
    const { w, namer } = world({ file: PENDING, answers: [{ exitCode: 0, stdout: '' }, { exitCode: 0, stdout: 'desk-uplink-keeper\n' }] })
    await namer.tick()
    w.files[SESSION] = PENDING.replace('desk-uplink-owner', 'desk-uplink-keeper')
    await namer.tick()
    expect(w.checks.length).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-keeper'])
  })

  test('while a main turn runs nothing is checked; the first idle tick after it renames', async () => {
    const { w, namer } = world({ file: PENDING })
    turnStarted(MAIN)
    await namer.tick()
    expect(w.checks).toEqual([])
    turnEnded(MAIN)
    await namer.tick()
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test("a subagent's turn is not the main turn", async () => {
    const { w, namer } = world({ file: PENDING })
    turnStarted(SUB)
    await namer.tick()
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test("while an ask's dialog is up nothing is checked; the first tick after it closes renames", async () => {
    const { w, namer } = world({ file: PENDING })
    w.isDialogUp = true
    await namer.tick()
    expect(w.checks).toEqual([])
    w.isDialogUp = false
    await namer.tick()
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test('a turn that starts while the check runs drops its answer and leaves the file for the next idle tick', async () => {
    const { w, namer } = world({ file: PENDING, during: once(() => turnStarted(MAIN)) })
    await namer.tick()
    expect(w.renames).toEqual([])
    await namer.tick()
    expect(w.checks.length).toBe(1)
    turnEnded(MAIN)
    await namer.tick()
    expect(w.checks.length).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test('a turn that starts and ends while the check runs still drops its answer', async () => {
    const { w, namer } = world({
      file: PENDING,
      during: once(() => {
        turnStarted(MAIN)
        turnEnded(MAIN)
      }),
    })
    await namer.tick()
    expect(w.renames).toEqual([])
    await namer.tick()
    expect(w.checks.length).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test('a turn that starts during the first dialog read and ends while the check runs drops its answer', async () => {
    const { w, namer } = world({
      file: PENDING,
      onDialogRead: (n) => {
        if (n === 1) {
          turnStarted(MAIN)
        }
      },
      during: once(() => turnEnded(MAIN)),
    })
    await namer.tick()
    expect(w.renames).toEqual([])
    await namer.tick()
    expect(w.checks.length).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test('a check that throws while a turn starts is left for the next idle tick too', async () => {
    const { w, namer } = world({
      file: PENDING,
      answers: [new Error('timed out'), { exitCode: 0, stdout: 'desk-uplink-owner\n' }],
      during: once(() => turnStarted(MAIN)),
    })
    await namer.tick()
    expect(w.renames).toEqual([])
    turnEnded(MAIN)
    await namer.tick()
    expect(w.checks.length).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test("an ask's dialog opened while the check runs holds the rename; the first tick after it closes checks again and renames", async () => {
    const { w, namer } = world({ file: PENDING, gated: true })
    const first = namer.tick()
    await settle()
    w.isDialogUp = true
    w.release()
    await first
    expect(w.renames).toEqual([])
    await namer.tick()
    expect(w.checks.length).toBe(1)
    w.isDialogUp = false
    const second = namer.tick()
    await settle()
    w.release()
    await second
    expect(w.checks.length).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test('a turn that starts while the dialog is read again holds the rename for the next idle tick', async () => {
    const { w, namer } = world({
      file: PENDING,
      onDialogRead: (n) => {
        if (n === 2) {
          turnStarted(MAIN)
        }
      },
    })
    await namer.tick()
    expect(w.renames).toEqual([])
    turnEnded(MAIN)
    await namer.tick()
    expect(w.checks.length).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test("a /clear while the check runs drops the attempt; the new session's own file is checked and applied on its own", async () => {
    const { w, namer } = world({
      file: PENDING,
      answers: [{ exitCode: 0, stdout: 'desk-uplink-owner\n' }, { exitCode: 0, stdout: 'desk-relay-keeper\n' }],
      during: once(() => {
        sessionEnded()
        w.session = OTHER
      }),
    })
    w.files[OTHER] = OTHER_PENDING
    await namer.tick()
    expect(w.renames).toEqual([])
    await namer.tick()
    expect(w.checks).toEqual([SESSION, OTHER])
    expect(w.renames).toEqual(['desk-relay-keeper'])
    expect(w.renamedIn).toEqual([OTHER])
  })

  test('a session id that moves with no session.end seen still drops the attempt', async () => {
    const { w, namer } = world({
      file: PENDING,
      during: once(() => {
        w.session = OTHER
      }),
    })
    await namer.tick()
    expect(w.renames).toEqual([])
  })

  test('a CLI that cannot run renames nothing, and is not tried again for the same file', async () => {
    const { w, namer } = world({ file: PENDING, answers: [new Error('timed out'), { exitCode: 0, stdout: 'desk-uplink-owner\n' }] })
    await namer.tick()
    await namer.tick()
    expect(w.checks.length).toBe(1)
    expect(w.renames).toEqual([])
  })

  test('a CLI that answers with an error renames nothing, and is not asked again for the same file', async () => {
    const { w, namer } = world({ file: PENDING, answers: [{ exitCode: 2, stdout: 'desk-uplink-owner\n' }] })
    await namer.tick()
    await namer.tick()
    expect(w.checks.length).toBe(1)
    expect(w.renames).toEqual([])
  })

  test('a rename the engine refuses goes to the debug log, and the file stays handled', async () => {
    const { w, namer } = world({ file: PENDING, refuse: true })
    await namer.tick()
    await namer.tick()
    expect(w.renames).toEqual(['desk-uplink-owner'])
    expect(w.logs.some((line) => line.includes('past a Stop'))).toBe(true)
  })

  test('a tick that lands while one is still running does nothing', async () => {
    const { w, namer } = world({ file: PENDING, gated: true })
    const first = namer.tick()
    await settle()
    await namer.tick()
    w.release()
    await first
    expect(w.checks.length).toBe(1)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })
})

/** A `$` of plain records for the session start: the env, the session, files, the CLI, the command, the clock's one timer. */
function engine(options: { env?: Record<string, string>; files?: Record<string, string>; dialog?: unknown } = {}) {
  const env = options.env ?? { HOME: '/home/u' }
  const files = options.files ?? {}
  const e = {
    reads: [] as string[],
    runs: [] as Array<{ argv: string[]; timeoutMs?: number }>,
    commands: [] as Array<{ command: string; args?: string }>,
    timers: [] as Array<{ ms: number; fn: () => unknown }>,
    stateReads: [] as unknown[],
  }
  const $ = {
    plugin: { root: '/plugin' },
    env: { get: async (name: string) => env[name] },
    session: { id: async () => SESSION },
    fs: {
      read: async (path: string) => {
        e.reads.push(path)
        const text = files[path]
        if (text === undefined) {
          throw new Error(`ENOENT: ${path}`)
        }
        return text
      },
    },
    process: {
      run: async (argv: string[], init?: { timeoutMs?: number }) => {
        e.runs.push({ argv, timeoutMs: init?.timeoutMs })
        return { exitCode: 0, stdout: 'desk-uplink-owner\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
      },
    },
    command: {
      run: async (input: { command: string; args?: string }) => {
        e.commands.push(input)
        return { text: `Session renamed to: ${input.args}` }
      },
    },
    state: {
      get: async (key: unknown) => {
        e.stateReads.push(key)
        return { value: options.dialog, version: 1 }
      },
    },
    clock: {
      every: (ms: number, fn: () => unknown) => {
        e.timers.push({ ms, fn })
        return { cancel: () => {} }
      },
    },
    ui: { log: () => {} },
  }
  resetName()
  return { e, $: $ as unknown as EngineInterface }
}

const FILE = `/home/u/.claude/sminos/names/${SESSION}.json`

/** Runs the one timer's tick and lets what it started settle. */
async function tick(e: { timers: Array<{ fn: () => unknown }> }) {
  await e.timers[0]?.fn()
  await settle()
}

describe('startNaming', () => {
  test("a timer every POLL_MS checks with the CLI and renames through the engine's /rename", async () => {
    const { e, $ } = engine({ files: { [FILE]: PENDING } })
    await startNaming($)
    expect(e.timers.map((t) => t.ms)).toEqual([POLL_MS])
    await tick(e)
    expect(e.runs).toEqual([{ argv: ['/plugin/skills/sminos/scripts/sminos', 'name-due', '--session', SESSION], timeoutMs: NAME_DUE_TIMEOUT_MS }])
    expect(e.commands).toEqual([{ command: 'rename', args: 'desk-uplink-owner' }])
  })

  test('an internal fork starts no timer and reads nothing', async () => {
    const { e, $ } = engine({ files: { [FILE]: PENDING }, env: { HOME: '/home/u', SMNS_INTERNAL: '1' } })
    await startNaming($)
    expect(e.timers).toEqual([])
    expect(e.reads).toEqual([])
  })

  test("an ask's dialog up, as the ask's snapshot says, holds the rename", async () => {
    const { e, $ } = engine({ files: { [FILE]: PENDING }, dialog: { isDialogUp: true } })
    await startNaming($)
    await tick(e)
    expect(e.stateReads).toEqual([{ plugin: 'sminos', key: 'ask' }])
    expect(e.runs).toEqual([])
    expect(e.commands).toEqual([])
  })

  test("the pending file is under the CLI's own home: SMINOS_HOME, else DAEMON_HOME, else ~/.claude/sminos", async () => {
    const reads: string[][] = []
    const envs: Array<Record<string, string>> = [
      { HOME: '/home/u', SMINOS_HOME: '/s', DAEMON_HOME: '/d' },
      { HOME: '/home/u', SMINOS_HOME: '', DAEMON_HOME: '/d' },
      { HOME: '/home/u' },
    ]
    for (const env of envs) {
      const { e, $ } = engine({ env })
      await startNaming($)
      await tick(e)
      reads.push(e.reads)
    }
    expect(reads).toEqual([[`/s/names/${SESSION}.json`], [`/d/names/${SESSION}.json`], [FILE]])
  })
})
