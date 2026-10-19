import { describe, expect, test, tier } from 'claude-code/testing'

import {
  FORCE_TEXT,
  RETRY_MS,
  changesOf,
  createReloader,
  parseInstalled,
  runningRecord,
  type InstallRecord,
  type Place,
} from '../../hooks/mods/reload'

tier('user')

const CACHE = '/h/.claude/plugins/cache'
const FILE = '/h/.claude/plugins/installed_plugins.json'
const at = (plugin: string, version: string) => `${CACHE}/dp/${plugin}/${version}`
const user = (plugin: string, version: string): InstallRecord => ({ scope: 'user', installPath: at(plugin, version), version })

const placeOf = (cwd: string, cwdRoot: string | null, existing: readonly string[]): Place => ({ cwd, cwdRoot, exists: async (path) => existing.includes(path) })

describe('parseInstalled', () => {
  test('reads the records by key, keeping only their string fields', async () => {
    const installed = parseInstalled(
      JSON.stringify({ version: 2, plugins: { 'a@m': [{ scope: 'user', installPath: '/p', version: '1', gitCommitSha: 'x' }, { scope: 'project', projectPath: 7 }, 'junk'] } }),
    )
    expect(installed).toEqual({ 'a@m': [{ scope: 'user', installPath: '/p', version: '1' }, { scope: 'project' }] })
  })

  test('a file mid-write or of another shape reads as nothing', async () => {
    expect(parseInstalled('{"plugins": {')).toBe(undefined)
    expect(parseInstalled('[]')).toBe(undefined)
    expect(parseInstalled('{"version": 2}')).toBe(undefined)
  })
})

describe('runningRecord', () => {
  const v1 = user('a', '1')
  const project = (projectPath: string, version: string): InstallRecord => ({ scope: 'project', projectPath, installPath: at('a', version), version })

  test('the first record that applies wins, a user record applying everywhere', async () => {
    const place = placeOf('/r', '/r', [at('a', '1'), at('a', '2')])
    expect(await runningRecord([v1, project('/r', '2')], place)).toEqual(v1)
    expect(await runningRecord([project('/r', '2'), v1], place)).toEqual(project('/r', '2'))
  })

  test("a project record applies at its own path and anywhere under its git root, not in a nested repository's", async () => {
    const place = placeOf('/r/sub', '/r', ['/r/.git', '/r/wt/.git', at('a', '2')])
    expect(await runningRecord([project('/r', '2')], place)).toEqual(project('/r', '2'))
    expect(await runningRecord([project('/r/other', '2')], place)).toEqual(project('/r/other', '2'))
    expect(await runningRecord([project('/r/wt', '2')], place)).toBe(undefined)
    expect(await runningRecord([project('/elsewhere', '2')], place)).toBe(undefined)
  })

  test('a record for an ancestor that is no git root of the session does not apply', async () => {
    const place = placeOf('/h/code/r', '/h/code/r', ['/h/code/r/.git'])
    expect(await runningRecord([{ scope: 'local', projectPath: '/h', installPath: '/x', version: '1' }], place)).toBe(undefined)
  })

  test('of several that apply, the first whose directory exists; none existing, the first', async () => {
    const both = [project('/r', '2'), v1]
    expect(await runningRecord(both, placeOf('/r', '/r', [at('a', '1')]))).toEqual(v1)
    expect(await runningRecord(both, placeOf('/r', '/r', []))).toEqual(project('/r', '2'))
  })
})

describe('changesOf', () => {
  test('a new install path is a change; an unchanged or removed plugin is not', async () => {
    const loaded = new Map([
      ['a@m', { path: '/a/1', version: '1' }],
      ['b@m', { path: '/b/1', version: '1' }],
      ['c@m', { path: '/c/1', version: '1' }],
    ])
    const now = new Map([
      ['a@m', { path: '/a/2', version: '2' }],
      ['b@m', { path: '/b/1', version: '1' }],
      ['c@m', {}],
    ])
    expect(changesOf(loaded, now)).toEqual([{ key: 'a@m', from: '1', to: '2' }])
  })
})

/**
 * A disk of plain records and an engine that writes down what the reloader
 * asks of it. `install` rewrites the file with a new mtime; the reload's
 * answer is set per test.
 */
function harness(options: { root?: string; enabled?: string[]; records?: Record<string, InstallRecord[]> } = {}) {
  let mtime = 1
  let plugins: Record<string, InstallRecord[]> = options.records ?? {
    'doperpowers@dp': [user('doperpowers', '7.1.0')],
    'to-human@dp': [user('to-human', '0.1.0')],
  }
  const existing = new Set(['/w/.git', ...Object.values(plugins).flatMap((rs) => rs.map((r) => r.installPath as string))])
  const calls: { op: string; text?: string }[] = []
  const state = {
    clock: 0,
    asks: 0,
    answer: (): Promise<{ text?: string }> => Promise.resolve({ text: 'Reloaded: 4 plugins · 30 skills' }),
  }
  const reloader = createReloader(
    {
      stat: async () => ({ mtimeMs: mtime }),
      read: async () => JSON.stringify({ version: 2, plugins }),
      exists: async (path) => existing.has(path),
      enabled: async () => new Set(options.enabled ?? Object.keys(plugins)),
      reload: () => (calls.push({ op: 'reload' }), state.answer()),
      asksInFlight: () => state.asks,
      now: () => state.clock,
      toast: (text) => calls.push({ op: 'toast', text }),
      log: (text, to) => calls.push({ op: `log:${to}`, text }),
    },
    { file: FILE, cacheDir: CACHE, cwd: '/w', self: { name: 'doperpowers', root: options.root ?? at('doperpowers', '7.1.0') } },
  )
  const install = (key: string, version: string) => {
    const plugin = key.split('@')[0] as string
    plugins = { ...plugins, [key]: [user(plugin, version)] }
    existing.add(at(plugin, version))
    mtime += 1
  }
  // Lets the reload's answer settle: a few microtask turns, no timer.
  const settle = async () => {
    for (let i = 0; i < 8; i++) {
      await Promise.resolve()
    }
  }
  const ticks = async (n: number) => {
    for (let i = 0; i < n; i++) {
      await reloader.tick()
      await settle()
    }
  }
  const reloads = () => calls.filter((c) => c.op === 'reload').length
  return { reloader, install, ticks, reloads, calls, state }
}

describe('createReloader', () => {
  test('nothing new installed, nothing reloaded', async () => {
    const h = harness()
    await h.reloader.start()
    await h.ticks(4)
    expect(h.reloads()).toBe(0)
  })

  test('an update reloads once the file has been quiet one period, and once only', async () => {
    const h = harness()
    await h.reloader.start()
    h.install('to-human@dp', '0.2.0')
    await h.ticks(1)
    expect(h.reloads()).toBe(0)
    await h.ticks(1)
    expect(h.reloads()).toBe(1)
    expect(h.calls.find((c) => c.op === 'toast')?.text).toBe('to-human 0.1.0 → 0.2.0: reloading plugins once the session is idle')
    await h.ticks(3)
    expect(h.reloads()).toBe(1)
    h.install('to-human@dp', '0.3.0')
    await h.ticks(2)
    expect(h.reloads()).toBe(2)
  })

  test('a roll of several plugins in a row reloads once', async () => {
    const h = harness()
    await h.reloader.start()
    h.install('doperpowers@dp', '7.2.0')
    await h.ticks(1)
    h.install('to-human@dp', '0.2.0')
    await h.ticks(1)
    expect(h.reloads()).toBe(0)
    await h.ticks(1)
    expect(h.reloads()).toBe(1)
    expect(h.calls.find((c) => c.op === 'toast')?.text).toBe('doperpowers 7.1.0 → 7.2.0, to-human 0.1.0 → 0.2.0: reloading plugins once the session is idle')
  })

  test('an open async question holds the reload until it is answered and delivered', async () => {
    const h = harness()
    await h.reloader.start()
    h.state.asks = 1
    h.install('doperpowers@dp', '7.2.0')
    await h.ticks(4)
    expect(h.reloads()).toBe(0)
    h.state.asks = 0
    await h.ticks(1)
    expect(h.reloads()).toBe(1)
  })

  test('a reload that needs --force is told to the person and not run again for that install', async () => {
    const h = harness()
    h.state.answer = () => Promise.resolve({ text: 'This reload … Run /reload-plugins --force to apply.' })
    await h.reloader.start()
    h.install('to-human@dp', '0.2.0')
    await h.ticks(5)
    expect(h.reloads()).toBe(1)
    expect(h.calls.filter((c) => c.op === 'log:transcript').map((c) => c.text)).toEqual([FORCE_TEXT])
    h.install('to-human@dp', '0.3.0')
    await h.ticks(2)
    expect(h.reloads()).toBe(2)
  })

  test('a reload the engine refused is tried again after the retry period', async () => {
    const h = harness()
    h.state.answer = () => Promise.reject(new Error('refused after a stop'))
    await h.reloader.start()
    h.install('to-human@dp', '0.2.0')
    await h.ticks(4)
    expect(h.reloads()).toBe(1)
    h.state.clock += RETRY_MS
    h.state.answer = () => Promise.resolve({ text: 'Reloaded: 4 plugins' })
    await h.ticks(1)
    expect(h.reloads()).toBe(2)
    await h.ticks(3)
    expect(h.reloads()).toBe(2)
  })

  test('this plugin is watched from the directory it runs from, and only a later change of the file reloads it', async () => {
    // The file already names 7.2.0, but the session runs 7.1.0.
    const h = harness({ records: { 'doperpowers@dp': [user('doperpowers', '7.2.0')] }, root: at('doperpowers', '7.1.0') })
    await h.reloader.start()
    await h.ticks(4)
    expect(h.reloads()).toBe(0)
    h.install('doperpowers@dp', '7.2.0')
    await h.ticks(2)
    expect(h.reloads()).toBe(1)
    expect(h.calls.find((c) => c.op === 'toast')?.text).toBe('doperpowers 7.1.0 → 7.2.0: reloading plugins once the session is idle')
  })

  test('a copy run from outside the cache (--plugin-dir) is not watched; a disabled plugin is not either', async () => {
    const dev = harness({ root: '/src/doperpowers', enabled: ['doperpowers@dp'] })
    await dev.reloader.start()
    dev.install('doperpowers@dp', '7.2.0')
    dev.install('to-human@dp', '0.2.0')
    await dev.ticks(4)
    expect(dev.reloads()).toBe(0)
  })
})
