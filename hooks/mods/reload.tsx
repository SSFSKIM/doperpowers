import type { On } from 'claude-code'

import { asksInFlight } from './ask'

/**
 * Plugin updates reach a running session on their own. The engine reads
 * installed_plugins.json once per process and tells no other session when one
 * installs a new version (`claude plugin update`, or a session's own
 * marketplace auto-update): each session runs the version it loaded until
 * `/reload-plugins`. This mod watches the file and, when a plugin the session
 * runs has a new install there, runs `/reload-plugins` itself, which the
 * engine queues until the session is idle; and one session per machine at a
 * time fetches the `autoUpdate` marketplaces' new versions, which the engine
 * does only at a session's start.
 */

/** One install record of installed_plugins.json, as the engine writes it. */
export type InstallRecord = { scope: string; installPath?: string; version?: string; projectPath?: string }

/** The records by plugin key (`<name>@<marketplace>`), in file order. */
export type Installed = Record<string, readonly InstallRecord[]>

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const text = (value: unknown) => (typeof value === 'string' ? value : undefined)

/** The file's records; undefined for a file that does not parse as one (mid-write, or another shape). */
export function parseInstalled(source: string): Installed | undefined {
  let data: unknown
  try {
    data = JSON.parse(source)
  } catch {
    return undefined
  }
  if (!isRecord(data) || !isRecord(data.plugins)) {
    return undefined
  }
  const installed: Record<string, InstallRecord[]> = {}
  for (const [key, records] of Object.entries(data.plugins)) {
    if (!Array.isArray(records)) {
      continue
    }
    installed[key] = records.filter(isRecord).flatMap((r) => {
      const scope = text(r.scope)
      if (scope === undefined) {
        return []
      }
      const [installPath, version, projectPath] = [text(r.installPath), text(r.version), text(r.projectPath)]
      return [{ scope, ...(installPath !== undefined && { installPath }), ...(version !== undefined && { version }), ...(projectPath !== undefined && { projectPath }) }]
    })
  }
  return installed
}

const parentOf = (dir: string) => dir.slice(0, dir.lastIndexOf('/')) || '/'

/** The nearest directory at or above `path` that holds a `.git`, walking no higher than `stop`; null when none. */
export async function gitRootOf(path: string, exists: (path: string) => Promise<boolean>, stop = '/'): Promise<string | null> {
  for (let dir = path; ; dir = parentOf(dir)) {
    if (await exists(`${dir === '/' ? '' : dir}/.git`)) {
      return dir
    }
    if (dir === stop || dir === '/') {
      return null
    }
  }
}

/** Where the session runs, for which records apply to it. */
export type Place = { cwd: string; cwdRoot: string | null; exists: (path: string) => Promise<boolean> }

/**
 * The engine's rule (2.1.302): a user or managed record applies everywhere; a
 * project or local one where its path is the session's directory or shares
 * its git root. Two paths share a root only if one lies inside the other's,
 * so only a path inside the session's root is walked.
 */
async function applies(record: InstallRecord, place: Place): Promise<boolean> {
  if (record.scope === 'user' || record.scope === 'managed') {
    return true
  }
  const project = record.projectPath
  if (project === undefined) {
    return false
  }
  if (project === place.cwd) {
    return true
  }
  const root = place.cwdRoot
  if (root === null || (project !== root && !project.startsWith(`${root}/`))) {
    return false
  }
  return (await gitRootOf(project, place.exists, root)) === root
}

/** The record the engine loads a plugin from: the first that applies whose directory exists, else the first that applies. */
export async function runningRecord(records: readonly InstallRecord[], place: Place): Promise<InstallRecord | undefined> {
  const applicable: InstallRecord[] = []
  for (const record of records) {
    if (record.installPath !== undefined && (await applies(record, place))) {
      applicable.push(record)
    }
  }
  if (applicable.length > 1) {
    for (const record of applicable) {
      if (await place.exists(record.installPath as string)) {
        return record
      }
    }
  }
  return applicable[0]
}

/** What a session runs, or would run after a reload, of each plugin: its install path and version. */
export type Snapshot = Map<string, { path?: string; version?: string }>

export async function snapshotOf(installed: Installed, keys: Iterable<string>, place: Place): Promise<Snapshot> {
  const snapshot: Snapshot = new Map()
  for (const key of keys) {
    const record = await runningRecord(installed[key] ?? [], place)
    snapshot.set(key, { ...(record?.installPath !== undefined && { path: record.installPath }), ...(record?.version !== undefined && { version: record.version }) })
  }
  return snapshot
}

export type Change = { key: string; from?: string; to?: string }

/** The plugins `loaded` runs that have another install now. An uninstall is not an update: it waits for the person's own reload. */
export function changesOf(loaded: Snapshot, now: Snapshot): Change[] {
  const changes: Change[] = []
  for (const [key, was] of loaded) {
    const is = now.get(key)
    if (is?.path !== undefined && is.path !== was.path) {
      changes.push({ key, ...(was.version !== undefined && { from: was.version }), ...(is.version !== undefined && { to: is.version }) })
    }
  }
  return changes
}

export function changeText(changes: readonly Change[]): string {
  return changes.map((c) => `${c.key.split('@')[0]} ${c.from ?? '?'} → ${c.to ?? '?'}`).join(', ')
}

/** How often the file is looked at; a change is acted on once the file has been quiet for one period, so a roll of several plugins reloads once. */
export const POLL_MS = 15_000
/** How long after a reload the engine refused (an Esc since the last input, a stop that dropped it) the next is tried. */
export const RETRY_MS = 60_000

export const FORCE_TEXT =
  'A plugin update is not applied: this reload would add or remove a plugin MCP or LSP server, so the next message re-reads the whole conversation. /reload-plugins --force applies it.'

/** What the reloader reaches the engine through; the session start makes it from `$`. */
export type ReloadIo = {
  stat: (path: string) => Promise<{ mtimeMs: number }>
  read: (path: string) => Promise<string>
  exists: (path: string) => Promise<boolean>
  /** The plugin keys the merged settings enable. */
  enabled: () => Promise<ReadonlySet<string>>
  /** `/reload-plugins`, queued until the session is idle; resolves to its output. */
  reload: () => Promise<{ text?: string }>
  asksInFlight: () => number
  now: () => number
  toast: (text: string) => void
  /** `transcript` for what the person must act on, `debug` for the rest. */
  log: (text: string, to: 'transcript' | 'debug') => void
}

export type ReloadWhere = {
  /** installed_plugins.json. */
  file: string
  /** The plugin cache, where an installed plugin runs from. */
  cacheDir: string
  cwd: string
  /** This plugin: its manifest name and the directory it runs from. */
  self: { name: string; root: string }
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

export function createReloader(io: ReloadIo, where: ReloadWhere) {
  const place: Place = { cwd: where.cwd, cwdRoot: null, exists: io.exists }
  let loaded: Snapshot = new Map()
  /** The file's mtime at the last look. */
  let seen: number | undefined
  /** The mtime whose records `due` was read from. */
  let read: number | undefined
  /** The changes the file holds against `loaded`, and the snapshot they lead to. */
  let due: { changes: Change[]; next: Snapshot } | undefined
  /** The mtime a reload was run for: one run per state of the file, so a plugin that will not load is not reloaded again and again. */
  let firedFor: number | undefined
  /** The mtime the person was told of: a reload the engine refused is tried again without telling them again. */
  let toastedFor: number | undefined
  let retryAt = 0
  let isBusy = false

  async function installed(): Promise<Installed | undefined> {
    return parseInstalled(await io.read(where.file))
  }

  function fire(mtime: number, changes: Change[], next: Snapshot) {
    firedFor = mtime
    if (toastedFor !== mtime) {
      toastedFor = mtime
      io.toast(`${changeText(changes)}: reloading plugins once the session is idle`)
    }
    // Where this plugin is among the changes, the reload retires this module
    // and neither branch runs; the new module starts from the file afresh.
    Promise.resolve().then(io.reload).then(
      (result) => {
        if (result.text?.includes('--force')) {
          io.toast(FORCE_TEXT)
          io.log(FORCE_TEXT, 'transcript')
          return
        }
        for (const change of changes) {
          loaded.set(change.key, next.get(change.key) ?? {})
        }
        due = undefined
      },
      (error) => {
        firedFor = undefined
        retryAt = io.now() + RETRY_MS
        io.log(`reload: /reload-plugins did not run (${message(error)}); trying again`, 'debug')
      },
    )
  }

  async function step() {
    const { mtimeMs } = await io.stat(where.file)
    if (mtimeMs !== seen) {
      seen = mtimeMs
      return
    }
    if (mtimeMs !== read) {
      read = mtimeMs
      const records = await installed()
      const next = records === undefined ? undefined : await snapshotOf(records, loaded.keys(), place)
      const changes = next === undefined ? [] : changesOf(loaded, next)
      due = next !== undefined && changes.length > 0 ? { changes, next } : undefined
      if (due !== undefined && io.asksInFlight() > 0) {
        io.log(`reload: ${changeText(due.changes)} waits for the open async questions`, 'debug')
      }
    }
    if (due === undefined || firedFor === mtimeMs || io.now() < retryAt || io.asksInFlight() > 0) {
      return
    }
    fire(mtimeMs, due.changes, due.next)
  }

  return {
    /** Reads what the session runs: each enabled installed plugin's record, this plugin's own directory for itself. */
    async start() {
      place.cwdRoot = await gitRootOf(where.cwd, io.exists)
      // Only a later change of the file is acted on, so the module a reload
      // starts never reloads again on its own, whatever it reads.
      seen = read = (await io.stat(where.file)).mtimeMs
      const records = await installed()
      const enabled = await io.enabled()
      const keys = Object.keys(records ?? {}).filter((key) => enabled.has(key))
      loaded = await snapshotOf(records ?? {}, keys, place)
      // This plugin runs from where the engine loaded it: exact, where the
      // file may have moved on since. A copy run from elsewhere (--plugin-dir)
      // is not the installed one, and the engine watches that folder itself.
      const isInstalled = where.self.root.startsWith(`${where.cacheDir}/`)
      for (const key of keys.filter((k) => k.split('@')[0] === where.self.name)) {
        if (isInstalled) {
          loaded.set(key, { path: where.self.root, version: where.self.root.slice(where.self.root.lastIndexOf('/') + 1) })
        } else {
          loaded.delete(key)
        }
      }
    },
    async tick() {
      if (isBusy) {
        return
      }
      isBusy = true
      try {
        await step()
      } catch (error) {
        io.log(`reload: ${message(error)}`, 'debug')
      } finally {
        isBusy = false
      }
    },
  }
}

/**
 * Fetching: the engine refreshes a marketplace marked `autoUpdate` once per
 * process, so a machine whose sessions run on gets nothing new until a session
 * starts or someone rolls it. One session per machine at a time, at most every
 * FETCH_MS and not while another actor rolls, asks each such marketplace's
 * remote for its head and, where it moved, updates the marketplace and the
 * enabled plugins installed from it at user scope; the watch above then
 * reloads every session on the machine.
 */
export const FETCH_MS = 5 * 60_000
/** A lock older than this was left by a session that died holding it. */
export const LOCK_STALE_MS = 30 * 60_000
/** A write to the engine's plugin state this recent is another actor rolling it, which the fetch waits out. */
export const ROLLING_MS = 60_000

export type Marketplace = { name: string; url: string; ref: string; clone: string }

/** The marketplaces known_marketplaces.json marks `autoUpdate` that come from a git remote, but none whose url or ref git would read as an option. */
export function autoUpdating(source: string): Marketplace[] {
  let data: unknown
  try {
    data = JSON.parse(source)
  } catch {
    return []
  }
  if (!isRecord(data)) {
    return []
  }
  return Object.entries(data).flatMap(([name, entry]) => {
    if (!isRecord(entry) || entry.autoUpdate !== true || !isRecord(entry.source)) {
      return []
    }
    const { source: kind, repo, url, ref } = entry.source
    const remote = kind === 'github' && typeof repo === 'string' ? `https://github.com/${repo}.git` : kind === 'git' ? text(url) : undefined
    const clone = text(entry.installLocation)
    const head = text(ref) ?? 'HEAD'
    return remote === undefined || clone === undefined || remote.startsWith('-') || head.startsWith('-') ? [] : [{ name, url: remote, ref: head, clone }]
  })
}

export type FetchIo = {
  /** Rejects when the path is missing. */
  stat: (path: string) => Promise<{ mtimeMs: number }>
  read: (path: string) => Promise<string>
  write: (path: string, text: string) => Promise<void>
  run: (argv: readonly string[], timeoutMs: number) => Promise<{ exitCode: number; stdout: string; stderr: string }>
  enabled: () => Promise<ReadonlySet<string>>
  now: () => number
  log: (text: string) => void
}

export type FetchWhere = {
  /** The engine's plugins directory: known_marketplaces.json, installed_plugins.json. */
  plugins: string
  /** The fetch's own directory, shared by the machine's sessions: its lock and its stamp. */
  state: string
}

const firstLine = (s: string) => s.trim().split('\n')[0] ?? ''
const lastLine = (s: string) => s.trim().split('\n').at(-1) ?? ''

export function createFetcher(io: FetchIo, where: FetchWhere) {
  const stamp = `${where.state}/fetch.stamp`
  const lock = `${where.state}/fetch.lock`
  let isBusy = false

  async function age(path: string): Promise<number | undefined> {
    try {
      return io.now() - (await io.stat(path)).mtimeMs
    } catch {
      return undefined
    }
  }

  const isFresh = async () => {
    const stamped = await age(stamp)
    return stamped !== undefined && stamped < FETCH_MS
  }

  /**
   * The lock serializes this mod's sessions only. The engine saves its two
   * files by read-modify-write with no lock, and refreshes a marketplace by
   * cloning beside it and renaming the clone in (2.1.283 on; before, a pull
   * into the clone, which writes its FETCH_HEAD). The fetch is due exactly
   * when the remote has just moved, which is when the person, the merging
   * session or a new session's auto-update rolls as well: a write to any of
   * these within ROLLING_MS is such an actor at work.
   */
  async function isRolling(marketplaces: readonly Marketplace[]): Promise<boolean> {
    const paths = new Set([`${where.plugins}/installed_plugins.json`, `${where.plugins}/known_marketplaces.json`])
    for (const m of marketplaces) {
      paths.add(parentOf(m.clone))
      paths.add(`${m.clone}/.git/FETCH_HEAD`)
    }
    for (const path of paths) {
      const since = await age(path)
      if (since !== undefined && since < ROLLING_MS) {
        return true
      }
    }
    return false
  }

  /** One marketplace: nothing when its clone is at the remote's head, else the marketplace and then its plugins updated. */
  async function fetchOne(m: Marketplace, installed: Installed, enabled: ReadonlySet<string>) {
    const remote = await io.run(['git', 'ls-remote', '--', m.url, m.ref], 30_000)
    const head = remote.exitCode === 0 ? firstLine(remote.stdout).split(/\s/)[0] : undefined
    if (head === undefined || head === '') {
      io.log(`reload: ${m.name}: the remote's head could not be read (${firstLine(remote.stderr) || `exit ${remote.exitCode}`})`)
      return
    }
    const local = await io.run(['git', '-C', m.clone, 'rev-parse', 'HEAD'], 10_000)
    if (local.exitCode === 0 && local.stdout.trim() === head) {
      return
    }
    const refreshed = await io.run(['claude', 'plugin', 'marketplace', 'update', m.name], 120_000)
    if (refreshed.exitCode !== 0) {
      io.log(`reload: ${m.name}: the marketplace did not update (${firstLine(refreshed.stderr) || firstLine(refreshed.stdout)})`)
      return
    }
    const keys = Object.keys(installed).filter((key) => key.endsWith(`@${m.name}`) && enabled.has(key) && installed[key]?.some((r) => r.scope === 'user'))
    for (const key of keys) {
      const updated = await io.run(['claude', 'plugin', 'update', key, '--scope', 'user'], 120_000)
      // The outcome is the CLI's last line, after its "Checking for updates…".
      io.log(`reload: ${key}: ${lastLine(updated.stdout) || lastLine(updated.stderr) || `exit ${updated.exitCode}`}`)
    }
  }

  async function step() {
    if (await isFresh()) {
      return
    }
    await io.run(['mkdir', '-p', where.state], 5_000)
    if ((await io.run(['mkdir', lock], 5_000)).exitCode !== 0) {
      const held = await age(lock)
      if (held !== undefined && held > LOCK_STALE_MS) {
        await io.run(['rmdir', lock], 5_000)
      }
      return
    }
    try {
      // Another session may have fetched between the look and the lock.
      if (await isFresh()) {
        return
      }
      // A machine without the file knows no marketplace, so has nothing to fetch.
      const marketplaces = autoUpdating(await io.read(`${where.plugins}/known_marketplaces.json`).catch(() => ''))
      // Unstamped, so a later look tries again once the other roll is done.
      if (await isRolling(marketplaces)) {
        io.log('reload: the plugin files changed within the minute; fetching at a later look')
        return
      }
      // Stamped before the fetch, so a fetch that fails is not retried by every session at once.
      await io.write(stamp, new Date(io.now()).toISOString())
      const installed = parseInstalled(await io.read(`${where.plugins}/installed_plugins.json`)) ?? {}
      const enabled = await io.enabled()
      for (const m of marketplaces) {
        await fetchOne(m, installed, enabled)
      }
    } finally {
      await io.run(['rmdir', lock], 5_000)
    }
  }

  return {
    async tick() {
      if (isBusy) {
        return
      }
      isBusy = true
      try {
        await step()
      } catch (error) {
        io.log(`reload: the fetch failed: ${message(error)}`)
      } finally {
        isBusy = false
      }
    },
  }
}

/** How often a session looks whether the machine's fetch is due. */
export const FETCH_LOOK_MS = 60_000

/**
 * Registers the watch and the fetch, in interactive sessions only: headless
 * runs refuse a plugin's `/reload-plugins`. `DOPERPOWERS_AUTORELOAD=off` (or
 * 0, false) leaves a launch on the versions it loaded and fetches nothing.
 */
export function registerReload(on: On) {
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    const result = await next(e)
    const off = await $.env.get('DOPERPOWERS_AUTORELOAD')
    if (off === 'off' || off === '0' || off === 'false') {
      return result
    }
    const config = (await $.env.get('CLAUDE_CONFIG_DIR')) ?? `${await $.env.get('HOME')}/.claude`
    const plugins = `${config}/plugins`
    const enabled = async () => {
      const { enabledPlugins } = await $.settings.read()
      return new Set(isRecord(enabledPlugins) ? Object.keys(enabledPlugins).filter((key) => enabledPlugins[key] === true) : [])
    }
    const fetcher = createFetcher(
      {
        stat: (path) => $.fs.stat(path),
        read: (path) => $.fs.read(path),
        write: (path, line) => $.fs.write(path, line),
        run: (argv, timeoutMs) => $.process.run(argv, { timeoutMs, env: { GIT_TERMINAL_PROMPT: '0' } }),
        enabled,
        now: () => Date.now(),
        log: (line) => $.ui.log(line, { to: 'debug' }),
      },
      { plugins, state: `${config}/autoreload` },
    )
    const reloader = createReloader(
      {
        stat: (path) => $.fs.stat(path),
        read: (path) => $.fs.read(path),
        exists: (path) => $.fs.exists(path),
        enabled,
        reload: () => $.command.run({ command: 'reload-plugins' }),
        asksInFlight,
        now: () => Date.now(),
        toast: (line) => $.ui.toast(line, { timeoutMs: 8000 }),
        log: (line, to) => $.ui.log(line, { to }),
      },
      { file: `${plugins}/installed_plugins.json`, cacheDir: `${plugins}/cache`, cwd: e.cwd, self: { name: $.plugin.name, root: $.plugin.root } },
    )
    void reloader.start().then(
      () => $.clock.every(POLL_MS, () => void reloader.tick()),
      (error) => $.ui.log(`reload: not watching plugin updates: ${message(error)}`, { to: 'debug' }),
    )
    $.clock.every(FETCH_LOOK_MS, () => void fetcher.tick())
    return result
  })
}
