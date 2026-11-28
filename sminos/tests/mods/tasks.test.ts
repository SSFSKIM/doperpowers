import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import { FORCED_TICKS, TICK_MS, registerTaskBand, registerTasks, resetTasks } from '../../hooks/mods/tasks'

tier('user')

// Every id, path and title here is invented.
const S1 = '5eed0000-0000-4000-8000-0000000000a1'
const S2 = '5eed0000-0000-4000-8000-0000000000a2'
const HOME = '/home/sm'

type Mine = { id: string; title: string; born: number }
const answer = (seq: number, open: [number, number], mine: Mine[] = [], board: { url: string } | null = null) =>
  JSON.stringify({ v: 1, seq, open: { count: open[0], blocking: open[1] }, mine, board })

type Handler = ($: EngineInterface, e: Record<string, unknown>, next: (e: Record<string, unknown>) => Promise<unknown>) => unknown

/**
 * The tasks' hooks in register.tsx's order (the band, then the reads) on an
 * engine of plain records: the command answers what the test queues (an Error
 * for a run that fails to start), each run held until released when `held`.
 */
function harness(options: { env?: Record<string, string>; held?: boolean } = {}) {
  resetTasks()
  const hooks: { event: string; matcher: Record<string, unknown>; handler: Handler }[] = []
  const on = ((event: string, matcher: Record<string, unknown>, handler: Handler) => {
    hooks.push({ event, matcher, handler })
    return { catch: () => undefined }
  }) as unknown as On
  registerTaskBand(on)
  registerTasks(on)
  const world = { session: S1, stat: 'file:10:1' as string | undefined }
  const answers: (string | Error | { exitCode: number })[] = []
  const runs: string[][] = []
  const notes: string[] = []
  const timers: { ms: number; fn: () => void }[] = []
  const releases: (() => void)[] = []
  let redraws = 0
  const $ = {
    plugin: { root: '/plug' },
    env: { get: async (name: string) => ({ SMINOS_HOME: HOME, ...options.env })[name] },
    session: { id: async () => world.session },
    process: {
      run: async (argv: string[]) => {
        runs.push(argv)
        if (options.held) await new Promise<void>((resolve) => releases.push(resolve))
        const a = answers.shift() ?? new Error('no answer queued')
        if (a instanceof Error) throw a
        return typeof a === 'string' ? { exitCode: 0, stdout: a, stderr: '' } : { exitCode: a.exitCode, stdout: '', stderr: 'refused' }
      },
    },
    fs: {
      stat: async (path: string) => {
        expect(path).toBe(`${HOME}/tasks/state.json`)
        if (world.stat === undefined) throw new Error('ENOENT')
        const [kind, size, mtimeMs] = world.stat.split(':')
        return { kind, size: Number(size), mtimeMs: Number(mtimeMs), isLink: false }
      },
    },
    ui: {
      notify: async (text: string) => {
        notes.push(text)
        return { isSent: true }
      },
      log: () => undefined,
      invalidate: () => {
        redraws += 1
      },
      resolve: () => ({ Box: 'Box', Text: 'Text' }),
    },
    clock: {
      every: (ms: number, fn: () => void) => {
        timers.push({ ms, fn })
        return () => undefined
      },
    },
  } as unknown as EngineInterface
  const settle = async () => {
    for (let i = 0; i < 50; i++) await Promise.resolve()
  }
  const fire = async (event: string, e: Record<string, unknown>) => {
    for (const hook of hooks.filter((x) => x.event === event)) await hook.handler($, e, async (passed) => passed)
    await settle()
  }
  const start = () => fire('session.start', { cwd: '/w' })
  const band = async (props: Record<string, unknown> = { hasSurvey: false }) => {
    const hook = hooks.find((x) => x.event === 'ui.render')!
    return hook.handler($, { component: 'AbovePrompt', props, surface: 'terminal' }, async () => 'beneath')
  }
  const tick = async (n = 1) => {
    for (let i = 0; i < n; i++) timers[0]!.fn()
    await settle()
  }
  const release = async () => {
    releases.shift()?.()
    await settle()
  }
  return { hooks, world, answers, runs, notes, timers, start, fire, band, tick, release, redraws: () => redraws }
}

/** The line a band holds above what was beneath. */
const lineOf = (drawn: unknown) => {
  const children = [(drawn as { children: unknown }).children].flat(2)
  const text = children[0] as { type: unknown; children: unknown }
  expect(text.type).toBe('Text')
  return [[text.children].flat(2).join(''), children[1]]
}


describe('the reads', () => {
  test('the start reads once, and a timer of five seconds is set', async () => {
    const h = harness()
    h.answers.push(answer(3, [0, 0]))
    await h.start()
    expect(h.runs).toEqual([['/plug/skills/sminos/scripts/sminos', 'task', 'status', '--session', S1, '--json']])
    expect(h.timers.map((t) => t.ms)).toEqual([TICK_MS])
  })

  test('a look reads only when the store or the session moved; every twelfth tick reads regardless', async () => {
    const h = harness()
    h.answers.push(answer(3, [0, 0]))
    await h.start()
    await h.tick(3)
    await h.fire('tool.call', { tool: 'Read' })
    expect(h.runs.length).toBe(1)
    h.world.stat = 'file:20:2'
    h.answers.push(answer(4, [1, 0]))
    await h.fire('turn.complete', { turnId: 't1' })
    expect(h.runs.length).toBe(2)
    h.world.session = S2
    h.answers.push(answer(4, [0, 0]))
    await h.fire('prompt.submit', { text: 'go' })
    expect(h.runs.at(-1)).toContain(S2)
    h.answers.push(answer(4, [0, 0]))
    await h.tick(FORCED_TICKS - 3)
    expect(h.runs.length).toBe(4)
  })

  test('a store that is not there is a stat like any other', async () => {
    const h = harness()
    h.world.stat = undefined
    h.answers.push(answer(0, [0, 0]))
    await h.start()
    await h.tick()
    expect(h.runs.length).toBe(1)
    h.world.stat = 'file:10:1'
    h.answers.push(answer(1, [1, 1]))
    await h.tick()
    expect(h.runs.length).toBe(2)
  })

  test('a failed read is tried again at the next look', async () => {
    for (const failure of [new Error('timed out'), { exitCode: 1 }, 'not json']) {
      const h = harness()
      h.answers.push(failure, answer(2, [1, 0]))
      await h.start()
      await h.tick()
      expect(h.runs.length).toBe(2)
      expect(lineOf(await h.band())[0]).toBe('1 task for the human · sminos task list')
    }
  })

  test('one read at a time; looks asked for while it runs make one more after it', async () => {
    const h = harness({ held: true })
    h.answers.push(answer(1, [0, 0]), answer(2, [0, 0]))
    await h.start()
    h.world.stat = 'file:30:3'
    await h.tick()
    await h.fire('tool.call', { tool: 'Bash' })
    expect(h.runs.length).toBe(1)
    await h.release()
    expect(h.runs.length).toBe(2)
    await h.release()
    await h.tick()
    expect(h.runs.length).toBe(2)
  })

  test('an internal fork registers nothing: no read and no timer', async () => {
    const h = harness({ env: { SMNS_INTERNAL: '1' } })
    await h.start()
    await h.fire('tool.call', { tool: 'Bash' })
    expect(h.runs).toEqual([])
    expect(h.timers).toEqual([])
    expect(await h.band()).toBe('beneath')
  })
})

describe('the notification', () => {
  test('once for a new blocking task, never for one open at the start', async () => {
    const h = harness()
    const old = { id: 't1', title: 'Rotate the key', born: 3 }
    h.answers.push(answer(5, [1, 1], [old]))
    await h.start()
    expect(h.notes).toEqual([])
    h.world.stat = 'file:11:2'
    h.answers.push(answer(7, [2, 2], [{ id: 't2', title: 'Log in to the console', born: 7 }, old]))
    await h.tick()
    expect(h.notes).toEqual(['A blocking task for you: Log in to the console'])
    h.world.stat = 'file:12:3'
    h.answers.push(answer(8, [2, 2], [{ id: 't2', title: 'Log in to the console', born: 7 }, old]))
    await h.tick()
    expect(h.notes.length).toBe(1)
  })

  test('the floor is the first answer adopted, not a read that failed', async () => {
    const h = harness()
    h.answers.push(new Error('busy'), answer(4, [1, 1], [{ id: 't4', title: 'Open the door', born: 4 }]))
    await h.start()
    await h.tick()
    expect(h.notes).toEqual([])
  })
})

describe('the line', () => {
  test('none, open, blocking, a board; drawn again when it changes; not while a survey holds the band', async () => {
    const h = harness()
    h.answers.push(answer(1, [0, 0]))
    await h.start()
    expect(await h.band()).toBe('beneath')
    const redraws = h.redraws()
    h.world.stat = 'file:2:2'
    h.answers.push(answer(2, [2, 1], [], { url: 'http://tasks.localhost:47590/board' }))
    await h.tick()
    expect(h.redraws()).toBe(redraws + 1)
    expect(lineOf(await h.band())).toEqual(['2 tasks for the human (1 blocking) · http://tasks.localhost:47590/board', 'beneath'])
    expect(await h.band({ hasSurvey: true })).toBe('beneath')
    h.world.stat = 'file:3:3'
    h.answers.push(answer(3, [2, 1], [], { url: 'http://tasks.localhost:47590/board' }))
    await h.tick()
    expect(h.redraws()).toBe(redraws + 1)
  })
})
