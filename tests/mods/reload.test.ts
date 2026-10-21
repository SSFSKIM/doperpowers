import { describe, expect, test, tier } from 'claude-code/testing'
import type { On } from 'claude-code'

import {
  APPLY_STALE_MS,
  FETCH_MS,
  FORCE_TEXT,
  LOCK_STALE_MS,
  RETRY_MS,
  ROLLING_MS,
  autoUpdating,
  changesOf,
  createFetcher,
  createReloader,
  heldText,
  isAskDialogUp,
  isMainTurnRunning,
  outputText,
  parseInstalled,
  registerReload,
  reloadRow,
  resetReload,
  runningRecord,
  type InstallRecord,
  type Place,
} from '../../hooks/mods/reload'
import { resetCompact } from '../../hooks/mods/compact'
import { register } from '../../hooks/mods/register'

tier('user')

const CACHE = '/h/.claude/plugins/cache'
const FILE = '/h/.claude/plugins/installed_plugins.json'
const FETCH_STATE = '/h/.claude/autoreload'
const APPLYING = `${FETCH_STATE}/fetch.applying`
const KNOWN = '/h/.claude/plugins/known_marketplaces.json'
const CLONE = '/h/.claude/plugins/marketplaces/dp'
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

type Manifest = { version?: string; dependencies?: string[] }

/**
 * A disk of plain records and an engine that writes down what the reloader
 * asks of it. `install` rewrites the file with a new mtime, and writes the
 * manifest of what it installs; the reload's answer is set per test. With a
 * `clone`, the marketplace's clone holds those files (`cloneOf`), which a
 * reload loads its path-sourced plugins from; without, every plugin loads
 * from its record, as one from a url does.
 */
function harness(
  options: { root?: string; enabled?: string[]; records?: Record<string, InstallRecord[]>; manifests?: Record<string, Manifest>; clone?: Record<string, unknown> } = {},
) {
  let mtime = 1
  let plugins: Record<string, InstallRecord[]> = options.records ?? {
    'doperpowers@dp': [user('doperpowers', '7.1.0')],
    'to-human@dp': [user('to-human', '0.1.0')],
  }
  const existing = new Set(['/w/.git', ...Object.values(plugins).flatMap((rs) => rs.map((r) => r.installPath as string))])
  const manifests = new Map(Object.entries(options.manifests ?? {}))
  const calls: { op: string; text?: string }[] = []
  const state = {
    clock: 0,
    isDialogUp: false,
    isTurnRunning: false,
    answer: (): Promise<{ text?: string }> => Promise.resolve({ text: 'Reloaded: 4 plugins · 30 skills' }),
    /** When the machine's fetch last marked that it applies a batch; undefined while it applies none. */
    applyingAt: undefined as number | undefined,
  }
  const MANIFEST = '/.claude-plugin/plugin.json'
  const reloader = createReloader(
    {
      stat: async (path) => {
        if (path !== APPLYING) {
          return { mtimeMs: mtime }
        }
        if (state.applyingAt === undefined) {
          throw new Error(`ENOENT: ${path}`)
        }
        return { mtimeMs: state.applyingAt }
      },
      read: async (path) => {
        if (path === FILE) {
          return JSON.stringify({ version: 2, plugins })
        }
        if (path === KNOWN && options.clone !== undefined) {
          return JSON.stringify({ dp: { source: { source: 'github', repo: 'o/dp' }, installLocation: CLONE, autoUpdate: true } })
        }
        const file = path.startsWith(`${CLONE}/`) ? options.clone?.[path.slice(CLONE.length + 1)] : path.endsWith(MANIFEST) ? manifests.get(path.slice(0, -MANIFEST.length)) : undefined
        if (file === undefined) {
          throw new Error(`ENOENT: ${path}`)
        }
        return JSON.stringify(file)
      },
      exists: async (path) => (path === APPLYING ? state.applyingAt !== undefined : existing.has(path)),
      enabled: async () => new Set(options.enabled ?? Object.keys(plugins)),
      reload: () => (calls.push({ op: 'reload' }), state.answer()),
      isAskDialogUp: () => state.isDialogUp,
      isTurnRunning: () => state.isTurnRunning,
      now: () => state.clock,
      toast: (text) => calls.push({ op: 'toast', text }),
      log: (text, to) => calls.push({ op: `log:${to}`, text }),
    },
    { file: FILE, cacheDir: CACHE, fetchState: FETCH_STATE, cwd: '/w', self: { name: 'doperpowers', root: options.root ?? at('doperpowers', '7.1.0') } },
  )
  const install = (key: string, version: string, manifest: Manifest = {}) => {
    const plugin = key.split('@')[0] as string
    plugins = { ...plugins, [key]: [user(plugin, version)] }
    existing.add(at(plugin, version))
    manifests.set(at(plugin, version), { name: plugin, version, ...manifest } as Manifest)
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

  test("an async question's dialog that is up holds the reload until it closes", async () => {
    const h = harness()
    await h.reloader.start()
    h.state.isDialogUp = true
    h.install('doperpowers@dp', '7.2.0')
    await h.ticks(4)
    expect(h.reloads()).toBe(0)
    h.state.isDialogUp = false
    await h.ticks(1)
    expect(h.reloads()).toBe(1)
  })

  test("a running turn holds the reload until it ends: queued then, it would run at the turn's end, ahead of a compaction asked for there", async () => {
    const h = harness()
    await h.reloader.start()
    h.state.isTurnRunning = true
    h.install('doperpowers@dp', '7.2.0')
    await h.ticks(4)
    expect(h.reloads()).toBe(0)
    h.state.isTurnRunning = false
    await h.ticks(1)
    expect(h.reloads()).toBe(1)
  })

  test("the machine's fetch applying a batch holds the reload, so the batch it is installing and updating reloads once, at its end", async () => {
    const h = harness()
    await h.reloader.start()
    h.state.applyingAt = h.state.clock
    h.install('doperpowers@dp', '7.2.0')
    await h.ticks(3)
    h.install('to-human@dp', '0.2.0')
    await h.ticks(3)
    expect(h.reloads()).toBe(0)
    h.state.applyingAt = undefined
    await h.ticks(1)
    expect(h.reloads()).toBe(1)
    expect(h.calls.find((c) => c.op === 'toast')?.text).toBe('doperpowers 7.1.0 → 7.2.0, to-human 0.1.0 → 0.2.0: reloading plugins once the session is idle')
  })

  test("a fetch's mark past its stale age, a few minutes, left by a session that died applying, holds nothing", async () => {
    const h = harness()
    await h.reloader.start()
    h.state.applyingAt = h.state.clock
    h.state.clock += APPLY_STALE_MS + 1
    h.install('to-human@dp', '0.2.0')
    await h.ticks(2)
    expect(h.reloads()).toBe(1)
    expect(APPLY_STALE_MS).toBeLessThan(LOCK_STALE_MS)
  })

  test('a changed plugin whose new manifest names a dependency not installed holds the reload, whoever updated it, and the reload fires once the dependency is installed', async () => {
    const h = harness()
    await h.reloader.start()
    h.install('to-human@dp', '0.2.0', { dependencies: ['sminos'] })
    await h.ticks(4)
    expect(h.reloads()).toBe(0)
    expect(h.calls.some((c) => c.op === 'log:debug' && c.text?.includes('to-human@dp') && c.text.includes('sminos@dp'))).toBe(true)
    h.install('sminos@dp', '1.0.0')
    await h.ticks(2)
    expect(h.reloads()).toBe(1)
    expect(h.calls.filter((c) => c.op === 'toast').at(-1)?.text).toBe('to-human 0.1.0 → 0.2.0: reloading plugins once the session is idle')
  })

  test('a dependency with a managed record counts as installed', async () => {
    const managed: InstallRecord = { scope: 'managed', installPath: at('sminos', '1.0.0'), version: '1.0.0' }
    const h = harness({ records: { 'doperpowers@dp': [user('doperpowers', '7.1.0')], 'to-human@dp': [user('to-human', '0.1.0')], 'sminos@dp': [managed] } })
    await h.reloader.start()
    h.install('to-human@dp', '0.2.0', { dependencies: ['sminos'] })
    await h.ticks(2)
    expect(h.reloads()).toBe(1)
  })

  test('the hold follows the dependency chain: a plugin over a dependency that waits for a missing one waits too, while an unrelated update reloads', async () => {
    const h = harness({ records: { 'a@dp': [user('a', '1')], 'b@dp': [user('b', '1')], 'd@dp': [user('d', '1')] } })
    await h.reloader.start()
    h.install('d@dp', '2')
    await h.ticks(2)
    expect(h.reloads()).toBe(1)
    h.install('b@dp', '2', { dependencies: ['c'] })
    h.install('a@dp', '2', { dependencies: ['b'] })
    await h.ticks(4)
    expect(h.reloads()).toBe(1)
    h.install('c@dp', '1')
    await h.ticks(2)
    expect(h.reloads()).toBe(2)
  })

  test("a plugin its marketplace carries by path is held on its clone's manifest, which the reload loads whatever its record says; one the clone holds at the version the session runs holds nothing", async () => {
    // The fetch updated doperpowers and held to-human back for sminos: a
    // reload would still load to-human 0.2.0 from the clone.
    const rolled = harness({ clone: cloneOf({ doperpowers: { version: '7.2.0' }, 'to-human': { version: '0.2.0', dependencies: ['sminos'] } }) })
    await rolled.reloader.start()
    rolled.install('doperpowers@dp', '7.2.0')
    await rolled.ticks(4)
    expect(rolled.reloads()).toBe(0)
    rolled.install('sminos@dp', '1.0.0')
    await rolled.ticks(2)
    expect(rolled.reloads()).toBe(1)
    // A dependency to-human named all along, never installed: the session
    // already runs without it, and a reload changes nothing of that.
    const standing = harness({ clone: cloneOf({ doperpowers: { version: '7.2.0' }, 'to-human': { version: '0.1.0', dependencies: ['gone'] } }) })
    await standing.reloader.start()
    standing.install('doperpowers@dp', '7.2.0')
    await standing.ticks(2)
    expect(standing.reloads()).toBe(1)
  })

  test('the hold is read again on the tick that would fire: a clone that moved under a pending reload, with no record written, holds it', async () => {
    const clone = cloneOf({ doperpowers: { version: '7.1.0' }, 'to-human': { version: '0.1.0' } })
    const h = harness({ clone })
    await h.reloader.start()
    h.state.isTurnRunning = true
    h.install('doperpowers@dp', '7.1.1')
    await h.ticks(4)
    expect(h.reloads()).toBe(0)
    // A marketplace update moves the clone and writes no record.
    Object.assign(clone, cloneOf({ doperpowers: { version: '7.2.0' }, 'to-human': { version: '0.2.0', dependencies: ['sminos'] } }))
    h.state.isTurnRunning = false
    await h.ticks(2)
    expect(h.reloads()).toBe(0)
  })

  test('a held reload is told in the transcript once, naming the plugin, the missing dependency and how to install it', async () => {
    const h = harness()
    await h.reloader.start()
    h.install('to-human@dp', '0.2.0', { dependencies: ['sminos'] })
    await h.ticks(6)
    expect(h.reloads()).toBe(0)
    const text = heldText('to-human@dp', 'sminos@dp')
    expect(text).toContain('/plugin install sminos@dp')
    expect(h.calls.filter((c) => c.op === 'log:transcript').map((c) => c.text)).toEqual([text])
    expect(h.calls.filter((c) => c.op === 'toast').map((c) => c.text)).toEqual([text])
    expect(h.calls.some((c) => c.op === 'log:debug' && c.text?.includes('would load without sminos@dp'))).toBe(true)
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
function fetchHarness(
  options: {
    remote?: string
    enabled?: string[]
    /** The clone's files, by path inside it, as JSON; one not named is missing. */
    clone?: Record<string, unknown>
    /** Install records beside the default ones. */
    records?: Record<string, InstallRecord[]>
    /** How long each git and claude command takes, on the fetch's clock. */
    slowMs?: number
    /** A second autoUpdate marketplace, `else`, fetched after `dp`; its clone holds no manifest. */
    withElse?: boolean
  } = {},
) {
  const PLUGINS = '/h/.claude/plugins'
  const STATE = '/h/.claude/autoreload'
  const CLONE = `${PLUGINS}/marketplaces/dp`
  const state = { clock: 1_000_000_000, remote: options.remote ?? 'b'.repeat(40), local: 'a'.repeat(40), failing: '' }
  const files = new Map<string, number>()
  const runs: string[] = []
  const logs: string[] = []
  const APPLYING = `${STATE}/fetch.applying`
  /** Each install and update, with whether the fetch's mark that it applies a batch was up as it ran. */
  const applied: { line: string; isMarked: boolean }[] = []
  const writes: string[] = []
  /** The mark's age as each git and claude command starts, while it is up. */
  const markAges: number[] = []
  const known = {
    dp: { source: { source: 'github', repo: 'o/dp' }, installLocation: CLONE, autoUpdate: true },
    ...(options.withElse && { else: { source: { source: 'github', repo: 'o/else' }, installLocation: `${PLUGINS}/marketplaces/else`, autoUpdate: true } }),
  }
  const installed = {
    version: 2,
    plugins: {
      'doperpowers@dp': [user('doperpowers', '7.1.0')],
      'to-human@dp': [user('to-human', '0.1.0')],
      'old@dp': [{ scope: 'project', projectPath: '/r', installPath: '/x', version: '1' }],
      'other@else': [user('other', '1')],
      ...options.records,
    } as Record<string, InstallRecord[]>,
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
      read: async (path) => {
        if (path.startsWith(`${CLONE}/`)) {
          const file = options.clone?.[path.slice(CLONE.length + 1)]
          if (file === undefined) {
            throw new Error(`ENOENT: ${path}`)
          }
          return JSON.stringify(file)
        }
        return JSON.stringify(path.endsWith('known_marketplaces.json') ? known : installed)
      },
      write: async (path) => {
        writes.push(path)
        files.set(path, state.clock)
      },
      run: async (argv) => {
        const isSlow = argv[0] === 'git' || argv[0] === 'claude'
        const markedAt = files.get(APPLYING)
        if (isSlow && markedAt !== undefined) {
          markAges.push(state.clock - markedAt)
        }
        const result = respond(argv)
        state.clock += isSlow ? (options.slowMs ?? 0) : 0
        return result
      },
      enabled: async () => new Set(options.enabled ?? ['doperpowers@dp', 'to-human@dp', 'old@dp', 'other@else', ...Object.keys(options.records ?? {})]),
      now: () => state.clock,
      log: (text) => void logs.push(text),
    },
    { plugins: PLUGINS, state: STATE },
  )
  function respond(argv: readonly string[]): { exitCode: number; stdout: string; stderr: string } {
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
    if (command === 'rm') {
      files.delete(argv.at(-1) as string)
    }
    if (line.startsWith('claude plugin install ') || line.startsWith('claude plugin update ')) {
      applied.push({ line, isMarked: files.has(APPLYING) })
    }
    if (first === 'ls-remote') {
      return ok(`${state.remote}\tHEAD\n`)
    }
    if (argv[3] === 'rev-parse') {
      return ok(`${state.local}\n`)
    }
    // The marketplace's update brings the clone to the remote's head; an install records the plugin.
    if (line.startsWith('claude plugin marketplace update')) {
      state.local = state.remote
    }
    if (line.startsWith('claude plugin install ')) {
      const key = argv[3] as string
      installed.plugins[key] = [user(key.split('@')[0] as string, 'new')]
    }
    // An update records the version the clone's manifest names.
    if (line.startsWith('claude plugin update ')) {
      const key = argv[3] as string
      const name = key.split('@')[0] as string
      const manifest = options.clone?.[`${name === 'doperpowers' ? '' : `${name}/`}.claude-plugin/plugin.json`] as { version?: string } | undefined
      if (manifest?.version !== undefined) {
        installed.plugins[key] = [user(name, manifest.version)]
      }
    }
    return ok()
  }
  const claude = () => runs.filter((r) => r.startsWith('claude '))
  return { fetcher, state, files, runs, logs, claude, applied, writes, markAges, plugins: PLUGINS, lock: `${STATE}/fetch.lock`, stamp: `${STATE}/fetch.stamp`, applying: APPLYING }
}

/**
 * A marketplace's clone as the engine checks it out: its marketplace.json,
 * and each plugin with a folder of the clone its manifest there. A plugin
 * from a url (ci-kit's) has no manifest in the clone.
 */
function cloneOf(plugins: Record<string, { version?: string; dependencies?: string[]; url?: string }>) {
  const sourceOf = (name: string) => (name === 'doperpowers' ? './' : `./${name}`)
  const files: Record<string, unknown> = {
    '.claude-plugin/marketplace.json': {
      name: 'dp',
      plugins: Object.entries(plugins).map(([name, p]) => ({ name, source: p.url !== undefined ? { source: 'url', url: p.url } : sourceOf(name) })),
    },
  }
  for (const [name, p] of Object.entries(plugins)) {
    if (p.url === undefined) {
      files[`${name === 'doperpowers' ? '' : `${name}/`}.claude-plugin/plugin.json`] = { name, ...(p.version !== undefined && { version: p.version }), ...(p.dependencies && { dependencies: p.dependencies }) }
    }
  }
  return files
}

describe('createFetcher: the plugins behind their clone', () => {
  const CI_KIT = { 'ci-kit@dp': [user('ci-kit', '892fccaa4429')] }
  const IN_PLACE = 'a'.repeat(40)

  test("a plugin behind its clone's manifest is updated though the remote's head has not moved; one at it, or one the clone holds no manifest of, is not", async () => {
    const h = fetchHarness({ remote: IN_PLACE, records: CI_KIT, clone: cloneOf({ doperpowers: { version: '7.2.0' }, 'to-human': { version: '0.1.0' }, 'ci-kit': { url: 'https://x/ci-kit.git' } }) })
    await h.fetcher.tick()
    expect(h.claude()).toEqual(['claude plugin update doperpowers@dp --scope user'])
  })

  test('a clone whose head is in place and whose versions match applies nothing', async () => {
    const h = fetchHarness({ remote: IN_PLACE, records: CI_KIT, clone: cloneOf({ doperpowers: { version: '7.1.0' }, 'to-human': { version: '0.1.0' }, 'ci-kit': { url: 'https://x/ci-kit.git' } }) })
    await h.fetcher.tick()
    expect(h.claude()).toEqual([])
  })

  test('a dependency the clone names that is not installed is installed first, then the plugins behind are updated, one the clone cannot tell on a moved head too', async () => {
    const clone = cloneOf({
      doperpowers: { version: '7.2.0' },
      'to-human': { version: '0.2.0', dependencies: ['sminos', 'doperpowers'] },
      sminos: { version: '1.0.0' },
      'ci-kit': { url: 'https://x/ci-kit.git' },
    })
    const h = fetchHarness({ records: CI_KIT, clone })
    await h.fetcher.tick()
    expect(h.claude()).toEqual([
      'claude plugin marketplace update dp',
      'claude plugin install sminos@dp --scope user',
      'claude plugin update doperpowers@dp --scope user',
      'claude plugin update to-human@dp --scope user',
      'claude plugin update ci-kit@dp --scope user',
    ])
  })

  test("a dependency that cannot be installed holds back the plugins depending on it, not the rest; the next fetch, the head in place but the version still behind, tries again", async () => {
    const clone = cloneOf({ doperpowers: { version: '7.2.0' }, 'to-human': { version: '0.2.0', dependencies: ['sminos'] }, sminos: { version: '1.0.0' } })
    const h = fetchHarness({ clone })
    h.state.failing = 'claude plugin install'
    await h.fetcher.tick()
    expect(h.claude()).toEqual(['claude plugin marketplace update dp', 'claude plugin install sminos@dp --scope user', 'claude plugin update doperpowers@dp --scope user'])
    expect(h.logs.some((line) => line.includes('to-human@dp') && line.includes('sminos@dp') && line.includes('held back'))).toBe(true)
    h.state.failing = ''
    h.state.clock += FETCH_MS
    await h.fetcher.tick()
    expect(h.claude().slice(3)).toEqual(['claude plugin install sminos@dp --scope user', 'claude plugin update to-human@dp --scope user'])
  })

  test("a missing dependency is installed though nothing is behind: another actor applied the update and left it out", async () => {
    const records = { 'doperpowers@dp': [user('doperpowers', '7.2.0')], 'to-human@dp': [user('to-human', '0.2.0')] }
    const h = fetchHarness({ remote: IN_PLACE, records, clone: cloneOf({ doperpowers: { version: '7.2.0' }, 'to-human': { version: '0.2.0', dependencies: ['sminos'] }, sminos: { version: '1.0.0' } }) })
    await h.fetcher.tick()
    expect(h.claude()).toEqual(['claude plugin install sminos@dp --scope user'])
  })

  test('a dependency with a managed record counts as installed', async () => {
    const records = { 'sminos@dp': [{ scope: 'managed', installPath: at('sminos', '1.0.0'), version: '1.0.0' }] }
    const h = fetchHarness({ remote: IN_PLACE, records, clone: cloneOf({ doperpowers: { version: '7.1.0' }, 'to-human': { version: '0.2.0', dependencies: ['sminos'] }, sminos: { version: '1.0.0' } }) })
    await h.fetcher.tick()
    expect(h.claude()).toEqual(['claude plugin update to-human@dp --scope user'])
  })

  test('the hold follows the dependency chain: a plugin over one held back for a dependency that will not install is held too, while an unrelated plugin updates', async () => {
    const records = { 'a@dp': [user('a', '1')], 'b@dp': [user('b', '1')], 'd@dp': [user('d', '1')] }
    const clone = cloneOf({ doperpowers: { version: '7.1.0' }, 'to-human': { version: '0.1.0' }, a: { version: '2', dependencies: ['b'] }, b: { version: '2', dependencies: ['c'] }, c: { version: '1' }, d: { version: '2' } })
    const h = fetchHarness({ remote: IN_PLACE, records, clone })
    h.state.failing = 'claude plugin install c@dp'
    await h.fetcher.tick()
    expect(h.claude()).toEqual(['claude plugin install c@dp --scope user', 'claude plugin update d@dp --scope user'])
    expect(h.logs.filter((line) => line.includes('held back'))).toEqual([expect.stringContaining('a@dp, b@dp')])
    h.state.failing = ''
    h.state.clock += FETCH_MS
    await h.fetcher.tick()
    expect(h.claude().slice(2)).toEqual(['claude plugin install c@dp --scope user', 'claude plugin update a@dp --scope user', 'claude plugin update b@dp --scope user'])
  })

  test('the fetch marks that it applies a batch through each install and update, and clears the mark after; a fetch with nothing to apply marks nothing', async () => {
    const h = fetchHarness({ clone: cloneOf({ doperpowers: { version: '7.2.0' }, 'to-human': { version: '0.2.0', dependencies: ['sminos'] }, sminos: { version: '1.0.0' } }) })
    await h.fetcher.tick()
    expect(h.applied.map((a) => a.isMarked)).toEqual([true, true, true])
    expect(h.files.has(h.applying)).toBe(false)
    const idle = fetchHarness({ remote: IN_PLACE, clone: cloneOf({ doperpowers: { version: '7.1.0' }, 'to-human': { version: '0.1.0' } }) })
    await idle.fetcher.tick()
    expect(idle.writes).not.toContain(idle.applying)
  })

  test("on a slow network the mark stays fresh through the whole batch, its marketplace's refresh and the next marketplace's look included", async () => {
    const h = fetchHarness({ withElse: true, slowMs: 100_000, clone: cloneOf({ doperpowers: { version: '7.2.0' }, 'to-human': { version: '0.2.0' } }) })
    await h.fetcher.tick()
    expect(h.claude()).toEqual(['claude plugin marketplace update dp', 'claude plugin update doperpowers@dp --scope user', 'claude plugin update to-human@dp --scope user'])
    expect(h.runs.filter((r) => r.includes('ls-remote'))).toHaveLength(2)
    expect(h.markAges.length).toBeGreaterThan(3)
    expect(Math.max(...h.markAges)).toBeLessThan(APPLY_STALE_MS)
    expect(h.files.has(h.applying)).toBe(false)
  })

  test("a dependency in another marketplace is installed under that marketplace's name", async () => {
    const h = fetchHarness({ remote: IN_PLACE, clone: cloneOf({ doperpowers: { version: '7.1.0' }, 'to-human': { version: '0.2.0', dependencies: ['tool@else'] } }) })
    await h.fetcher.tick()
    expect(h.claude()).toEqual(['claude plugin install tool@else --scope user', 'claude plugin update to-human@dp --scope user'])
  })
})

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
    expect(h.runs.filter((r) => r.includes('ls-remote'))).toHaveLength(2)
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

// A plugin's `/reload-plugins` as the engine appends it (2.1.302/303): the
// caveat and the command line from the plugin's origin, the output a
// `local_command` notice from the engine's.
const SELF = { kind: 'plugin', name: 'doperpowers' }
const PERSON = { kind: 'composer' }
const ENGINE = { kind: 'engine' }
const userRow = (text: string, isMeta = false) => ({ type: 'user', role: 'user', ...(isMeta && { isMeta: true }), content: [{ type: 'text', text }] })
const CAVEAT = userRow('<local-command-caveat>The command below was run directly in Claude Code, not sent to you as a request.</local-command-caveat>', true)
const COMMAND = userRow('<command-name>/reload-plugins</command-name>\n<command-message>reload-plugins</command-message>\n<command-args></command-args>')
const OUTPUT = { type: 'system', name: 'local_command', role: 'user', content: [{ type: 'text', text: '<local-command-stdout>Reloaded: 10 plugins · 24 skills</local-command-stdout>' }] }

describe('reloadRow', () => {
  test("reads this plugin's caveat and reload line, and the output that follows the line", async () => {
    expect(reloadRow(CAVEAT, SELF, 'doperpowers', false)).toBe('caveat')
    expect(reloadRow(COMMAND, SELF, 'doperpowers', false)).toBe('command')
    expect(reloadRow(OUTPUT, ENGINE, 'doperpowers', true)).toBe('output')
  })

  test("leaves the person's, another plugin's, another command's, and an output no reload line went before", async () => {
    expect(reloadRow(COMMAND, PERSON, 'doperpowers', false)).toBeUndefined()
    expect(reloadRow(CAVEAT, { kind: 'plugin', name: 'cua' }, 'doperpowers', false)).toBeUndefined()
    expect(reloadRow(userRow('<command-name>/kairos</command-name>'), SELF, 'doperpowers', false)).toBeUndefined()
    expect(reloadRow(OUTPUT, ENGINE, 'doperpowers', false)).toBeUndefined()
    expect(reloadRow({ ...OUTPUT, name: 'informational' }, ENGINE, 'doperpowers', true)).toBeUndefined()
  })

  test('the output text drops its tag, an error\'s too', async () => {
    expect(outputText(OUTPUT.content)).toBe('Reloaded: 10 plugins · 24 skills')
    expect(outputText([{ type: 'text', text: '<local-command-stderr>Failed to reload: boom</local-command-stderr>' }])).toBe('Failed to reload: boom')
  })
})

describe("what the reload waits for, read without the ask's module: sminos's ask snapshot and the engine's turns", () => {
  /** The module's hooks on a fake `on`, and a session start whose engine has sminos's snapshot as `ask`. */
  function startHarness() {
    const hooks: { event: string; matcher: Record<string, unknown> | undefined; handler: (...args: unknown[]) => unknown }[] = []
    resetReload()
    registerReload(((event: string, ...rest: unknown[]) => {
      hooks.push({ event, matcher: rest.length > 1 ? (rest[0] as Record<string, unknown>) : undefined, handler: rest[rest.length - 1] as (...args: unknown[]) => unknown })
      return { catch: () => undefined }
    }) as unknown as On)
    const hook = (event: string, e: Record<string, unknown>) => {
      const found = hooks.filter((h) => h.event === event && Object.entries(h.matcher ?? {}).every(([k, v]) => (v instanceof RegExp ? v.test(String(e[k])) : e[k] === v)))
      expect(found.length).toBe(1)
      return found[0]!.handler
    }
    const engine = (ask: unknown) => ({
      plugin: { name: 'doperpowers', root: '/src/doperpowers' },
      env: { get: async (name: string) => (name === 'HOME' ? '/h' : undefined) },
      settings: { read: async () => ({ enabledPlugins: {} }) },
      fs: { stat: async () => Promise.reject(new Error('ENOENT')), read: async () => Promise.reject(new Error('ENOENT')), exists: async () => false },
      clock: { every: () => ({ cancel: () => undefined }) },
      ui: { log: () => undefined, toast: () => undefined },
      state: { get: async (ref: { plugin: string; key: string }) => (ref.plugin === 'sminos' && ref.key === 'ask' && ask !== undefined ? { value: ask, version: 3 } : { value: undefined, version: 0 }) },
    })
    const start = (ask?: unknown) => hook('session.start', { isInteractive: true })(engine(ask), { cwd: '/w', isInteractive: true }, async () => ({}))
    const write = (value: unknown) =>
      hook('state.set', { plugin: 'sminos', key: 'ask' })(engine(value), { plugin: 'sminos', key: 'ask', value }, async () => ({ isSet: true, version: 4 }))
    const turn = (event: 'turn.start' | 'turn.complete', agentId?: string) =>
      hook(event, { turnId: 't1' })(engine(undefined), { turnId: 't1', ...(agentId !== undefined && { agentId }) }, async () => ({}))
    return { start, write, turn }
  }
  const SNAPSHOT = { shape: 2, asks: [], undelivered: [], isTurnRunning: false, answered: 0 }

  test('a dialog already up when the module starts (a reload of doperpowers alone) is read at the session start', async () => {
    const h = startHarness()
    await h.start({ ...SNAPSHOT, isDialogUp: true })
    expect(isAskDialogUp()).toBe(true)
  })

  test("then each write of the snapshot keeps it: the dialog's close lets the reload run", async () => {
    const h = startHarness()
    await h.start({ ...SNAPSHOT, isDialogUp: false })
    expect(isAskDialogUp()).toBe(false)
    expect(await h.write({ ...SNAPSHOT, isDialogUp: true })).toEqual({ isSet: true, version: 4 })
    expect(isAskDialogUp()).toBe(true)
    await h.write({ ...SNAPSHOT, isDialogUp: false })
    expect(isAskDialogUp()).toBe(false)
  })

  test('with sminos absent no value is ever written, which reads as no dialog', async () => {
    const h = startHarness()
    await h.start()
    expect(isAskDialogUp()).toBe(false)
    await h.write(undefined)
    expect(isAskDialogUp()).toBe(false)
  })

  test("the main turn is the engine's: running from its start to its end; a subagent's turns are not it", async () => {
    const h = startHarness()
    await h.start()
    await h.turn('turn.start', 'a1')
    expect(isMainTurnRunning()).toBe(false)
    await h.turn('turn.start')
    expect(isMainTurnRunning()).toBe(true)
    await h.turn('turn.complete', 'a1')
    expect(isMainTurnRunning()).toBe(true)
    await h.turn('turn.complete')
    expect(isMainTurnRunning()).toBe(false)
  })
})

describe("the main turn the reload waits on, through the plugin's hooks in their registered order", () => {
  test("it runs until the compaction the compact tool asked for at the turn's end has run", async () => {
    resetReload()
    resetCompact()
    const hooks: { event: string; matcher: Record<string, unknown> | undefined; handler: (...args: unknown[]) => unknown }[] = []
    register(((event: string, ...rest: unknown[]) => {
      hooks.push({ event, matcher: rest.length > 1 ? (rest[0] as Record<string, unknown>) : undefined, handler: rest[rest.length - 1] as (...args: unknown[]) => unknown })
      return { catch: () => undefined }
    }) as unknown as On)
    let isRunningWhileCompacting: boolean | undefined
    const $ = {
      session: {
        compact: async () => {
          isRunningWhileCompacting = isMainTurnRunning()
          return { messages: [] }
        },
      },
      prompt: { submit: async () => ({}) },
      ui: { log: () => undefined, toast: () => undefined },
    }
    /** `e` down every hook of `event` that matches it, the first registered outermost, as the engine nests one module's hooks. */
    const dispatch = (event: string, e: Record<string, unknown>) => {
      const chain = hooks.filter((h) => h.event === event && Object.entries(h.matcher ?? {}).every(([k, v]) => (v instanceof RegExp ? v.test(String(e[k])) : e[k] === v)))
      const at = (i: number, input: Record<string, unknown>): unknown =>
        i === chain.length ? {} : chain[i]!.handler($, input, async (inner: Record<string, unknown>) => at(i + 1, inner))
      return at(0, e)
    }
    await dispatch('turn.start', { turnId: 't1', text: '' })
    const tool = hooks.find((h) => h.event === 'tool.call' && h.matcher?.tool === 'mcp__doperpowers__compact')!
    await tool.handler($, { tool: 'mcp__doperpowers__compact', resume: 'go on' }, async () => ({}))
    await dispatch('turn.complete', { turnId: 't1', reason: 'answer' })
    expect(isRunningWhileCompacting).toBe(true)
    expect(isMainTurnRunning()).toBe(false)
  })
})

describe("a reload's rows", () => {
  function rowsHarness() {
    const hooks: { event: string; matcher: unknown; handler: (...args: unknown[]) => unknown }[] = []
    registerReload(((event: string, matcher: unknown, handler: (...args: unknown[]) => unknown) => {
      hooks.push({ event, matcher, handler })
    }) as unknown as On)
    const logged: unknown[][] = []
    const toasted: unknown[][] = []
    const $ = {
      plugin: { name: 'doperpowers' },
      ui: { log: (...args: unknown[]) => logged.push(args), toast: (...args: unknown[]) => toasted.push(args) },
    }
    const hook = hooks.find((h) => h.event === 'session.append')!
    expect(hook.matcher).toEqual({ door: 'command' })
    const stored: unknown[] = []
    const append = async (message: Record<string, unknown>, origin: unknown) => {
      await hook.handler($, { message, door: 'command', origin, uuid: 'u' }, async (e: { message: unknown }) => (stored.push(e.message), { message: e.message, uuid: 'u' }))
    }
    return { append, stored, logged, toasted }
  }

  test("each row of this plugin's reload is kept empty, and a reload that went through reaches the person as a toast", async () => {
    const h = rowsHarness()
    await h.append(CAVEAT, SELF)
    await h.append(COMMAND, SELF)
    await h.append(OUTPUT, ENGINE)
    expect(h.stored).toEqual([
      { ...CAVEAT, content: [] },
      { ...COMMAND, content: [] },
      { ...OUTPUT, content: [] },
    ])
    expect(h.toasted).toEqual([['/reload-plugins: Reloaded: 10 plugins · 24 skills', { timeoutMs: 8000 }]])
    expect(h.logged).toEqual([])
  })

  test('a reload whose output says more, or that failed, stays as the plugin\'s transcript line', async () => {
    for (const text of ['Reloaded: 10 plugins · 24 skills\n1 error during load. Run /plugin for details.', 'Failed to reload plugins: ENOENT']) {
      const h = rowsHarness()
      await h.append(COMMAND, SELF)
      await h.append({ ...OUTPUT, content: [{ type: 'text', text: `<local-command-stdout>${text}</local-command-stdout>` }] }, ENGINE)
      expect(h.logged).toEqual([[`/reload-plugins: ${text}`]])
      expect(h.toasted).toEqual([])
    }
  })

  test("the person's own reload passes whole, its output too", async () => {
    const h = rowsHarness()
    await h.append(CAVEAT, PERSON)
    await h.append(COMMAND, PERSON)
    await h.append(OUTPUT, ENGINE)
    expect(h.stored).toEqual([CAVEAT, COMMAND, OUTPUT])
    expect(h.logged).toEqual([])
  })

  test('an output after any other row than the reload line passes', async () => {
    const h = rowsHarness()
    await h.append(COMMAND, SELF)
    await h.append(userRow('<command-name>/context</command-name>'), PERSON)
    await h.append(OUTPUT, ENGINE)
    expect(h.stored).toEqual([{ ...COMMAND, content: [] }, userRow('<command-name>/context</command-name>'), OUTPUT])
  })
})
