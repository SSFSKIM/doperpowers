import { describe, expect, test, tier } from 'claude-code/testing'

import {
  FETCH_MS,
  FORCE_TEXT,
  LOCK_STALE_MS,
  RETRY_MS,
  ROLLING_MS,
  autoUpdating,
  changesOf,
  createFetcher,
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
    isTurnRunning: false,
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
      isTurnRunning: () => state.isTurnRunning,
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

  test("a running turn holds the reload until it ends: queued then, it would run at the turn's end, past a question the turn asked meanwhile", async () => {
    const h = harness()
    await h.reloader.start()
    h.state.isTurnRunning = true
    h.install('doperpowers@dp', '7.2.0')
    await h.ticks(4)
    expect(h.reloads()).toBe(0)
    h.state.asks = 1
    h.state.isTurnRunning = false
    await h.ticks(2)
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

  test('a reload the engine refused is tried again after the retry period, and the person told once', async () => {
    const h = harness()
    h.state.answer = () => Promise.reject(new Error('refused after a stop'))
    await h.reloader.start()
    h.install('to-human@dp', '0.2.0')
    await h.ticks(4)
    expect(h.reloads()).toBe(1)
    h.state.clock += RETRY_MS
    await h.ticks(1)
    expect(h.reloads()).toBe(2)
    h.state.clock += RETRY_MS
    h.state.answer = () => Promise.resolve({ text: 'Reloaded: 4 plugins' })
    await h.ticks(1)
    expect(h.reloads()).toBe(3)
    await h.ticks(3)
    expect(h.reloads()).toBe(3)
    const toasts = () => h.calls.filter((c) => c.op === 'toast')
    expect(toasts()).toHaveLength(1)
    expect(h.calls.filter((c) => c.op === 'log:debug')).toHaveLength(2)
    h.install('to-human@dp', '0.3.0')
    await h.ticks(2)
    expect(toasts()).toHaveLength(2)
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

describe('autoUpdating', () => {
  test('reads the git marketplaces marked autoUpdate, with their remote, ref and clone', async () => {
    const known = {
      dp: { source: { source: 'github', repo: 'o/dp' }, installLocation: '/m/dp', autoUpdate: true },
      pinned: { source: { source: 'git', url: 'https://x/p.git', ref: 'stable' }, installLocation: '/m/p', autoUpdate: true },
      official: { source: { source: 'github', repo: 'a/official' }, installLocation: '/m/o' },
      local: { source: { source: 'directory', path: '/src/l' }, installLocation: '/src/l', autoUpdate: true },
    }
    expect(autoUpdating(JSON.stringify(known))).toEqual([
      { name: 'dp', url: 'https://github.com/o/dp.git', ref: 'HEAD', clone: '/m/dp' },
      { name: 'pinned', url: 'https://x/p.git', ref: 'stable', clone: '/m/p' },
    ])
    expect(autoUpdating('{')).toEqual([])
  })

  test('an entry whose url or ref git would read as an option is left out', async () => {
    const known = {
      url: { source: { source: 'git', url: '--upload-pack=touch /tmp/x' }, installLocation: '/m/u', autoUpdate: true },
      ref: { source: { source: 'github', repo: 'o/r', ref: '-q' }, installLocation: '/m/r', autoUpdate: true },
    }
    expect(autoUpdating(JSON.stringify(known))).toEqual([])
  })
})

/**
 * A machine's files and commands as plain records: the remote's head and the
 * clone's, the mtimes of the stamp and the lock, and every command run
 * written down.
 */
function fetchHarness(options: { remote?: string; enabled?: string[] } = {}) {
  const PLUGINS = '/h/.claude/plugins'
  const STATE = '/h/.claude/autoreload'
  const state = { clock: 1_000_000_000, remote: options.remote ?? 'b'.repeat(40), failing: '' }
  const files = new Map<string, number>()
  const runs: string[] = []
  const known = { dp: { source: { source: 'github', repo: 'o/dp' }, installLocation: `${PLUGINS}/marketplaces/dp`, autoUpdate: true } }
  const installed = {
    version: 2,
    plugins: {
      'doperpowers@dp': [user('doperpowers', '7.1.0')],
      'to-human@dp': [user('to-human', '0.1.0')],
      'old@dp': [{ scope: 'project', projectPath: '/r', installPath: '/x', version: '1' }],
      'other@else': [user('other', '1')],
    },
  }
  const ok = (stdout = '') => ({ exitCode: 0, stdout, stderr: '' })
  const fetcher = createFetcher(
    {
      stat: async (path) => {
        const mtime = files.get(path)
        if (mtime === undefined) {
          throw new Error(`ENOENT: ${path}`)
        }
        return { mtimeMs: mtime }
      },
      read: async (path) => JSON.stringify(path.endsWith('known_marketplaces.json') ? known : installed),
      write: async (path) => void files.set(path, state.clock),
      run: async (argv) => {
        const line = argv.join(' ')
        runs.push(line)
        if (state.failing !== '' && line.startsWith(state.failing)) {
          return { exitCode: 1, stdout: '', stderr: 'failed' }
        }
        const [command, first] = argv
        if (command === 'mkdir' && first !== '-p') {
          if (files.has(first as string)) {
            return { exitCode: 1, stdout: '', stderr: 'File exists' }
          }
          files.set(first as string, state.clock)
        }
        if (command === 'rmdir') {
          files.delete(first as string)
        }
        if (first === 'ls-remote') {
          return ok(`${state.remote}\tHEAD\n`)
        }
        if (argv[3] === 'rev-parse') {
          return ok(`${'a'.repeat(40)}\n`)
        }
        return ok()
      },
      enabled: async () => new Set(options.enabled ?? ['doperpowers@dp', 'to-human@dp', 'old@dp', 'other@else']),
      now: () => state.clock,
      log: () => {},
    },
    { plugins: PLUGINS, state: STATE },
  )
  const claude = () => runs.filter((r) => r.startsWith('claude '))
  return { fetcher, state, files, runs, claude, plugins: PLUGINS, lock: `${STATE}/fetch.lock`, stamp: `${STATE}/fetch.stamp` }
}

describe('createFetcher', () => {
  test('a moved remote updates the marketplace, then each enabled plugin installed from it at user scope', async () => {
    const h = fetchHarness()
    await h.fetcher.tick()
    expect(h.claude()).toEqual([
      'claude plugin marketplace update dp',
      'claude plugin update doperpowers@dp --scope user',
      'claude plugin update to-human@dp --scope user',
    ])
    expect(h.files.has(h.lock)).toBe(false)
    expect(h.files.has(h.stamp)).toBe(true)
  })

  test('a clone at the remote head updates nothing', async () => {
    const h = fetchHarness({ remote: 'a'.repeat(40) })
    await h.fetcher.tick()
    expect(h.runs).toContain('git ls-remote -- https://github.com/o/dp.git HEAD')
    expect(h.claude()).toEqual([])
  })

  test('the machine fetches at most once a period, whichever session looks', async () => {
    const h = fetchHarness()
    await h.fetcher.tick()
    const once = h.runs.length
    h.state.clock += FETCH_MS - 1
    await h.fetcher.tick()
    expect(h.runs.length).toBe(once)
    h.state.clock += 1
    await h.fetcher.tick()
    expect(h.claude().filter((r) => r.includes('marketplace update'))).toHaveLength(2)
  })

  test('a lock another session holds is left alone; one past the stale age is cleared for the next look', async () => {
    const h = fetchHarness()
    h.files.set(h.lock, h.state.clock)
    await h.fetcher.tick()
    expect(h.runs.some((r) => r.includes('ls-remote'))).toBe(false)
    expect(h.files.has(h.lock)).toBe(true)
    h.state.clock += LOCK_STALE_MS + 1
    await h.fetcher.tick()
    expect(h.files.has(h.lock)).toBe(false)
    await h.fetcher.tick()
    expect(h.claude()).toHaveLength(3)
  })

  test("a write to the plugin state within the minute is another actor's roll: the round waits for a later look, unstamped", async () => {
    // The two files; the clone's directory, where 2.1.283 on swaps a new clone in; its FETCH_HEAD, which a pull into it writes.
    for (const written of ['installed_plugins.json', 'known_marketplaces.json', 'marketplaces', 'marketplaces/dp/.git/FETCH_HEAD']) {
      const h = fetchHarness()
      h.files.set(`${h.plugins}/${written}`, h.state.clock - ROLLING_MS + 1)
      await h.fetcher.tick()
      expect(h.runs.some((r) => r.includes('ls-remote'))).toBe(false)
      expect(h.files.has(h.stamp)).toBe(false)
      expect(h.files.has(h.lock)).toBe(false)
      h.state.clock += 1
      await h.fetcher.tick()
      expect(h.claude()).toHaveLength(3)
    }
  })

  test('a marketplace that will not update leaves its plugins alone, and the lock is released', async () => {
    const h = fetchHarness()
    h.state.failing = 'claude plugin marketplace update'
    await h.fetcher.tick()
    expect(h.claude()).toEqual(['claude plugin marketplace update dp'])
    expect(h.files.has(h.lock)).toBe(false)
  })

  test('a disabled plugin is not updated', async () => {
    const h = fetchHarness({ enabled: ['doperpowers@dp'] })
    await h.fetcher.tick()
    expect(h.claude()).toEqual(['claude plugin marketplace update dp', 'claude plugin update doperpowers@dp --scope user'])
  })
})
