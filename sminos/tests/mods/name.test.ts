import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface } from 'claude-code'

import { NAME_DUE_TIMEOUT_MS, POLL_MS, createNamer, resetName, startNaming, turnEnded, turnStarted } from '../../hooks/mods/name'
import type { NameIo } from '../../hooks/mods/name'

tier('user')

const SESSION = '1a000001-0000-4000-8000-000000000001'
const PENDING = `{"session": "${SESSION}", "name": "desk-uplink-owner", "from": "work-0b", "line": "Owns the desk's uplink.", "ts": "2026-10-20T10:00:00Z"}`

type Answer = { exitCode: number; stdout: string } | Error

/**
 * The namer's world as plain records: the pending file, the CLI's answers in
 * turn, the turn and dialog as set here. Every read, check and rename is
 * logged. `during` runs while the CLI answers (a turn that starts meanwhile).
 */
function world(options: { file?: string; answers?: Answer[]; during?: () => void } = {}) {
  const w = {
    file: options.file as string | undefined,
    isDialogUp: false,
    reads: 0,
    checks: 0,
    renames: [] as string[],
    logs: [] as string[],
  }
  const answers = [...(options.answers ?? [{ exitCode: 0, stdout: 'desk-uplink-owner\n' }])]
  resetName()
  const io: NameIo = {
    read: async () => {
      w.reads += 1
      if (w.file === undefined) {
        throw new Error('ENOENT')
      }
      return w.file
    },
    due: async () => {
      w.checks += 1
      options.during?.()
      const a = answers.length > 1 ? answers.shift() : answers[0]
      if (a instanceof Error) {
        throw a
      }
      return a ?? { exitCode: 0, stdout: '' }
    },
    rename: async (name) => {
      w.renames.push(name)
    },
    isAskDialogUp: async () => w.isDialogUp,
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

const MAIN = { turnId: 't1' } as never
const SUB = { turnId: 't2', agentId: 'a1' } as never

describe('createNamer', () => {
  test('an idle tick with a due name renames the session once; the same file at a later tick runs no second check', async () => {
    const { w, namer } = world({ file: PENDING })
    await namer.tick()
    expect(w.renames).toEqual(['desk-uplink-owner'])
    await namer.tick()
    await namer.tick()
    expect(w.checks).toBe(1)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test('no pending file: the CLI is never run', async () => {
    const { w, namer } = world()
    await namer.tick()
    await namer.tick()
    expect(w.reads).toBe(2)
    expect(w.checks).toBe(0)
    expect(w.renames).toEqual([])
  })

  test('a name that is not due renames nothing, and is not asked again for the same file', async () => {
    const { w, namer } = world({ file: PENDING, answers: [{ exitCode: 0, stdout: '' }] })
    await namer.tick()
    await namer.tick()
    expect(w.checks).toBe(1)
    expect(w.renames).toEqual([])
  })

  test('a new pending file is checked afresh', async () => {
    const { w, namer } = world({ file: PENDING, answers: [{ exitCode: 0, stdout: '' }, { exitCode: 0, stdout: 'desk-uplink-keeper\n' }] })
    await namer.tick()
    w.file = PENDING.replace('desk-uplink-owner', 'desk-uplink-keeper')
    await namer.tick()
    expect(w.checks).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-keeper'])
  })

  test('while a main turn runs nothing is checked; the first idle tick after it renames', async () => {
    const { w, namer } = world({ file: PENDING })
    turnStarted(MAIN)
    await namer.tick()
    expect(w.checks).toBe(0)
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
    expect(w.checks).toBe(0)
    w.isDialogUp = false
    await namer.tick()
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test("a turn that starts while the check runs drops its answer and leaves the file for the next idle tick", async () => {
    let first = true
    const { w, namer } = world({
      file: PENDING,
      during: () => {
        if (first) {
          first = false
          turnStarted(MAIN)
        }
      },
    })
    await namer.tick()
    expect(w.renames).toEqual([])
    await namer.tick()
    expect(w.checks).toBe(1)
    turnEnded(MAIN)
    await namer.tick()
    expect(w.checks).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test('a turn that starts and ends while the check runs still drops its answer', async () => {
    let first = true
    const { w, namer } = world({
      file: PENDING,
      during: () => {
        if (first) {
          first = false
          turnStarted(MAIN)
          turnEnded(MAIN)
        }
      },
    })
    await namer.tick()
    expect(w.renames).toEqual([])
    await namer.tick()
    expect(w.checks).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test('a check that throws while a turn starts is left for the next idle tick too', async () => {
    let first = true
    const { w, namer } = world({
      file: PENDING,
      answers: [new Error('timed out'), { exitCode: 0, stdout: 'desk-uplink-owner\n' }],
      during: () => {
        if (first) {
          first = false
          turnStarted(MAIN)
        }
      },
    })
    await namer.tick()
    expect(w.renames).toEqual([])
    turnEnded(MAIN)
    await namer.tick()
    expect(w.checks).toBe(2)
    expect(w.renames).toEqual(['desk-uplink-owner'])
  })

  test("an ask's dialog opened while the check runs holds the rename; the first tick after it closes checks again and renames", async () => {
    let release: () => void = () => {}
    let isDialogUp = false
    let checks = 0
    const renames: string[] = []
    resetName()
    const namer = createNamer({
      read: async () => PENDING,
      due: () =>
        new Promise((resolve) => {
          checks += 1
          release = () => resolve({ exitCode: 0, stdout: 'desk-uplink-owner\n' })
        }),
      rename: async (name) => {
        renames.push(name)
      },
      isAskDialogUp: async () => isDialogUp,
      log: () => {},
    })
    const first = namer.tick()
    await settle()
    isDialogUp = true
    release()
    await first
    expect(renames).toEqual([])
    await namer.tick()
    expect(checks).toBe(1)
    isDialogUp = false
    const second = namer.tick()
    await settle()
    release()
    await second
    expect(checks).toBe(2)
    expect(renames).toEqual(['desk-uplink-owner'])
  })

  test('a turn that starts while the dialog is read again holds the rename for the next idle tick', async () => {
    let reads = 0
    let checks = 0
    const renames: string[] = []
    resetName()
    const namer = createNamer({
      read: async () => PENDING,
      due: async () => {
        checks += 1
        return { exitCode: 0, stdout: 'desk-uplink-owner\n' }
      },
      rename: async (name) => {
        renames.push(name)
      },
      isAskDialogUp: async () => {
        reads += 1
        if (reads === 2) {
          turnStarted(MAIN)
        }
        return false
      },
      log: () => {},
    })
    await namer.tick()
    expect(renames).toEqual([])
    turnEnded(MAIN)
    await namer.tick()
    expect(checks).toBe(2)
    expect(renames).toEqual(['desk-uplink-owner'])
  })

  test('a CLI that cannot run renames nothing, and is not tried again for the same file', async () => {
    const { w, namer } = world({ file: PENDING, answers: [new Error('timed out'), { exitCode: 0, stdout: 'desk-uplink-owner\n' }] })
    await namer.tick()
    await namer.tick()
    expect(w.checks).toBe(1)
    expect(w.renames).toEqual([])
  })

  test('a CLI that answers with an error renames nothing, and is not asked again for the same file', async () => {
    const { w, namer } = world({ file: PENDING, answers: [{ exitCode: 2, stdout: 'desk-uplink-owner\n' }] })
    await namer.tick()
    await namer.tick()
    expect(w.checks).toBe(1)
    expect(w.renames).toEqual([])
  })

  test('a rename the engine refuses goes to the debug log, and the file stays handled', async () => {
    const { w } = world()
    const refusing = createNamer({
      read: async () => PENDING,
      due: async () => ({ exitCode: 0, stdout: 'desk-uplink-owner\n' }),
      rename: async () => {
        w.renames.push('tried')
        throw new Error('past a Stop')
      },
      isAskDialogUp: async () => false,
      log: (line) => w.logs.push(line),
    })
    await refusing.tick()
    await refusing.tick()
    expect(w.renames).toEqual(['tried'])
    expect(w.logs.some((line) => line.includes('past a Stop'))).toBe(true)
  })

  test('a tick that lands while one is still running does nothing', async () => {
    let release: () => void = () => {}
    const { w } = world()
    const slow = createNamer({
      read: async () => PENDING,
      due: () =>
        new Promise((resolve) => {
          w.checks += 1
          release = () => resolve({ exitCode: 0, stdout: 'desk-uplink-owner\n' })
        }),
      rename: async (name) => {
        w.renames.push(name)
      },
      isAskDialogUp: async () => false,
      log: () => {},
    })
    const first = slow.tick()
    await settle()
    await slow.tick()
    release()
    await first
    expect(w.checks).toBe(1)
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
