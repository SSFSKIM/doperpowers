import type { On } from 'claude-code'

/**
 * Plugin updates reach a running session on their own. The engine reads
 * installed_plugins.json once per process and tells no other session when one
 * installs a new version (`claude plugin update`, or a session's own
 * marketplace auto-update): each session runs the version it loaded until
 * `/reload-plugins`. This mod watches the file and, when a plugin the session
 * runs has a new install there, runs `/reload-plugins` itself while the
 * session is idle and nothing it would load lacks a dependency; and one
 * session per machine at a time fetches the `autoUpdate` marketplaces' new
 * versions, which the engine does only at a session's start, and installs
 * the dependencies they name. The rows such a reload leaves are kept out of
 * what the model reads (see `reloadRow`).
 */

/** One install record of installed_plugins.json, as the engine writes it. */
export type InstallRecord = { scope: string; installPath?: string; version?: string; projectPath?: string }

/** The records by plugin key (`<name>@<marketplace>`), in file order. */
export type Installed = Record<string, readonly InstallRecord[]>

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const text = (value: unknown) => (typeof value === 'string' ? value : undefined)

/** A plugin is installed, as a dependency, with a user or managed record: one the engine loads everywhere. */
export const isInstalledIn = (installed: Installed, key: string) => installed[key]?.some((r) => r.scope === 'user' || r.scope === 'managed') === true

/** A plugin as its manifest names it: its version, and the plugins it depends on, by key. */
export type PluginManifest = { version?: string; dependencies: string[] }

/** A manifest's fields; a dependency named without a marketplace is of the dependent's, as the engine reads it. */
function manifestOf(data: Record<string, unknown>, marketplace: string): PluginManifest {
  const version = text(data.version)
  const dependencies = (Array.isArray(data.dependencies) ? data.dependencies : [])
    .filter((dependency): dependency is string => typeof dependency === 'string')
    .map((dependency) => (dependency.includes('@') ? dependency : `${dependency}@${marketplace}`))
  return { ...(version !== undefined && { version }), dependencies }
}

async function readJson(read: (path: string) => Promise<string>, path: string): Promise<Record<string, unknown> | undefined> {
  try {
    const data: unknown = JSON.parse(await read(path))
    return isRecord(data) ? data : undefined
  } catch {
    return undefined
  }
}

const marketplaceOf = (key: string) => key.slice(key.indexOf('@') + 1)

/**
 * The missing plugin a plugin's dependency chain reaches, if any: a plugin is
 * held when one it depends on is missing or itself held, so a dependent never
 * lands over a dependency that is held back.
 */
export async function missingInChain(
  key: string,
  dependencies: (key: string) => Promise<readonly string[]>,
  isMissing: (key: string) => boolean,
  seen = new Set<string>(),
): Promise<string | undefined> {
  seen.add(key)
  for (const dependency of await dependencies(key)) {
    if (isMissing(dependency)) {
      return dependency
    }
    const reached = seen.has(dependency) ? undefined : await missingInChain(dependency, dependencies, isMissing, seen)
    if (reached !== undefined) {
      return reached
    }
  }
  return undefined
}

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

/** A reload held for a missing dependency: one plugin at a new clone version holds every reload on the machine, so the person is told, as a transcript line no request carries. */
export const heldText = (key: string, missing: string) =>
  `A plugin update is not applied: ${key} would load without ${missing}, which is not installed. /plugin install ${missing} installs it, and the reload follows.`

/** What the reloader reaches the engine through; the session start makes it from `$`. */
export type ReloadIo = {
  stat: (path: string) => Promise<{ mtimeMs: number }>
  read: (path: string) => Promise<string>
  exists: (path: string) => Promise<boolean>
  /** The plugin keys the merged settings enable. */
  enabled: () => Promise<ReadonlySet<string>>
  /** `/reload-plugins`, queued until the session is idle; resolves to its output. */
  reload: () => Promise<{ text?: string }>
  /** An async ask's dialog is up: the module that raised it takes its answer, and one a reload starts meanwhile would show it open still. */
  isAskDialogUp: () => boolean
  /** A main turn is running, so a reload run now would wait for its end. */
  isTurnRunning: () => boolean
  now: () => number
  toast: (text: string) => void
  /** `transcript` for what the person must act on, `debug` for the rest. */
  log: (text: string, to: 'transcript' | 'debug') => void
}

export type ReloadWhere = {
  /** installed_plugins.json; known_marketplaces.json is beside it. */
  file: string
  /** The plugin cache, where an installed plugin runs from. */
  cacheDir: string
  /** The machine's fetch's directory (`createFetcher`), where it marks that it applies a batch. */
  fetchState: string
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
  /** The changes the file holds against `loaded`, the snapshot they lead to, and the records they were read from. */
  let due: { changes: Change[]; next: Snapshot; records: Installed } | undefined
  /** The hold the person was told of, so each is told once. */
  let toldHeld: string | undefined
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

  /**
   * The machine's fetch is installing and updating a batch of plugins: the
   * file moves at each, maybe more than a period apart, and a reload at each
   * gap would reload every idle session again, and load what is not yet
   * updated of the batch. A mark past its stale age was left by a session
   * that died applying.
   */
  async function isApplying(): Promise<boolean> {
    try {
      return io.now() - (await io.stat(fetchFiles(where.fetchState).applying)).mtimeMs < APPLY_STALE_MS
    } catch {
      return false
    }
  }

  /**
   * The plugin a reload would change that would load over a missing
   * dependency, whoever wrote the records. A plugin its marketplace carries
   * by path loads at its clone's manifest whatever its record says (see the
   * README), so it changes when that version is not the one the session
   * runs, and its dependencies are the clone's; any other loads its record's
   * install. A plugin whose loaded version already lacked a dependency holds
   * nothing: the reload leaves it as it was.
   */
  async function heldBy(records: Installed, changes: readonly Change[]): Promise<{ key: string; missing: string } | undefined> {
    const known = await readJson(io.read, `${parentOf(where.file)}/known_marketplaces.json`)
    const cloned = new Map<string, PluginManifest>()
    for (const name of new Set([...loaded.keys()].map(marketplaceOf))) {
      const entry = known?.[name]
      const clone = isRecord(entry) ? text(entry.installLocation) : undefined
      if (clone !== undefined) {
        for (const [key, manifest] of await cloneManifests({ name, clone }, io.read)) {
          cloned.set(key, manifest)
        }
      }
    }
    const dependencies = async (key: string) => {
      const manifest = cloned.get(key)
      if (manifest !== undefined) {
        return manifest.dependencies
      }
      const path = (await runningRecord(records[key] ?? [], place))?.installPath
      const data = path === undefined ? undefined : await readJson(io.read, `${path}/.claude-plugin/plugin.json`)
      return data === undefined ? [] : manifestOf(data, marketplaceOf(key)).dependencies
    }
    const changing = new Set(changes.map((c) => c.key))
    for (const [key, was] of loaded) {
      const version = cloned.get(key)?.version
      if (version !== undefined && version !== was.version) {
        changing.add(key)
      }
    }
    for (const key of changing) {
      const missing = await missingInChain(key, dependencies, (dependency) => !isInstalledIn(records, dependency))
      if (missing !== undefined) {
        return { key, missing }
      }
    }
    return undefined
  }

  async function step() {
    const { mtimeMs } = await io.stat(where.file)
    if (mtimeMs !== seen) {
      seen = mtimeMs
      return
    }
    if (mtimeMs !== read) {
      read = mtimeMs
      due = undefined
      const records = await installed()
      if (records !== undefined) {
        const next = await snapshotOf(records, loaded.keys(), place)
        const changes = changesOf(loaded, next)
        due = changes.length > 0 ? { changes, next, records } : undefined
      }
    }
    // Only while the session is idle, where the reload runs at once: queued
    // during a turn, it would run at the turn's end, ahead of a compaction
    // the model asked for at that end, which then fails. The ask mod keeps
    // its open questions across the reload, but not a dialog it has up. And
    // not while the machine's fetch is mid-batch, so a roll reloads once.
    if (due === undefined || firedFor === mtimeMs || io.now() < retryAt || io.isAskDialogUp() || io.isTurnRunning() || (await isApplying())) {
      return
    }
    // Nor into a plugin whose dependency is missing, read on the tick that
    // fires: a marketplace update moves the clone, which the reload loads,
    // and writes no record. The dependency's install writes one.
    const held = await heldBy(due.records, due.changes)
    if (held !== undefined) {
      if (toldHeld !== `${held.key} ${held.missing}`) {
        toldHeld = `${held.key} ${held.missing}`
        io.log(`reload: ${changeText(due.changes)} waits: ${held.key} would load without ${held.missing}, which is not installed`, 'debug')
        io.toast(heldText(held.key, held.missing))
        io.log(heldText(held.key, held.missing), 'transcript')
      }
      return
    }
    toldHeld = undefined
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
 * remote for its head and, where it moved, updates the marketplace; then,
 * moved or not, installs every plugin the enabled plugins' manifests in the
 * clone depend on that is not installed, whoever updated those plugins, and
 * updates the enabled plugins installed from it at user scope whose version
 * is not their manifest's in the clone, but none whose dependency chain
 * reaches one that did not install. The watch above then reloads every
 * session on the machine, once the batch is done.
 */
export const FETCH_MS = 5 * 60_000
/** A lock older than this was left by a session that died holding it. */
export const LOCK_STALE_MS = 30 * 60_000
/** How long one plugin or marketplace command may run. */
const PLUGIN_COMMAND_MS = 120_000
/** The fetch marks that it applies a batch afresh before each of its commands once one is under way, so a mark older than one command's run and a margin was left by a session that died applying. */
export const APPLY_STALE_MS = PLUGIN_COMMAND_MS + 60_000
/** A write to the engine's plugin state this recent is another actor rolling it, which the fetch waits out. */
export const ROLLING_MS = 60_000

/** The fetch's files in its directory: its stamp, its lock, and its mark that it applies a batch. */
export const fetchFiles = (state: string) => ({ stamp: `${state}/fetch.stamp`, lock: `${state}/fetch.lock`, applying: `${state}/fetch.applying` })

export type Marketplace = { name: string; url: string; ref: string; clone: string }

/**
 * The manifests a marketplace's clone holds, by plugin key: each plugin its
 * marketplace.json lists from a folder of the clone. A plugin from elsewhere
 * (a url) has none there, nor one whose manifest does not read.
 */
export async function cloneManifests(m: Pick<Marketplace, 'name' | 'clone'>, read: (path: string) => Promise<string>): Promise<Map<string, PluginManifest>> {
  const manifests = new Map<string, PluginManifest>()
  const listing = await readJson(read, `${m.clone}/.claude-plugin/marketplace.json`)
  for (const entry of Array.isArray(listing?.plugins) ? listing.plugins : []) {
    if (!isRecord(entry) || typeof entry.name !== 'string' || typeof entry.source !== 'string') {
      continue
    }
    const folder = entry.source.replace(/^\.\/?/, '').replace(/\/+$/, '')
    const manifest = await readJson(read, `${m.clone}${folder === '' ? '' : `/${folder}`}/.claude-plugin/plugin.json`)
    if (manifest !== undefined) {
      manifests.set(`${entry.name}@${m.name}`, manifestOf(manifest, m.name))
    }
  }
  return manifests
}

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
  const { stamp, lock, applying } = fetchFiles(where.state)
  let isBusy = false
  /** The fetch marked that it applies a batch, so clears the mark at its end. */
  let isMarked = false

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
   * into the clone, which writes its FETCH_HEAD). The fetch finds work
   * mostly just after the remote moved, which is when the person, the
   * merging session or a new session's auto-update rolls as well: a write to
   * any of these within ROLLING_MS is such an actor at work.
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

  /**
   * Before a marketplace's update and each install and update, and afresh
   * before the next marketplace's look once a batch is under way, so the
   * mark's age stays under one command's run until the batch ends.
   */
  async function mark() {
    await io.write(applying, new Date(io.now()).toISOString())
    isMarked = true
  }

  /**
   * One marketplace: updated where its clone is behind the remote's head;
   * then every plugin its enabled plugins' chains depend on that is not
   * installed is installed, whoever updated them; then its enabled plugins
   * behind the clone are updated, but none whose chain reaches a dependency
   * that did not install. The next fetch tries that one again, and the
   * plugins it held back are behind still.
   */
  async function fetchOne(m: Marketplace, installed: Installed, enabled: ReadonlySet<string>) {
    if (isMarked) {
      await mark()
    }
    const remote = await io.run(['git', 'ls-remote', '--', m.url, m.ref], 30_000)
    const head = remote.exitCode === 0 ? firstLine(remote.stdout).split(/\s/)[0] : undefined
    if (head === undefined || head === '') {
      io.log(`reload: ${m.name}: the remote's head could not be read (${firstLine(remote.stderr) || `exit ${remote.exitCode}`})`)
      return
    }
    const local = await io.run(['git', '-C', m.clone, 'rev-parse', 'HEAD'], 10_000)
    const isMoved = local.exitCode !== 0 || local.stdout.trim() !== head
    if (isMoved) {
      // The new clone is what a reload loads its path-sourced plugins from.
      await mark()
      const refreshed = await io.run(['claude', 'plugin', 'marketplace', 'update', m.name], PLUGIN_COMMAND_MS)
      if (refreshed.exitCode !== 0) {
        io.log(`reload: ${m.name}: the marketplace did not update (${firstLine(refreshed.stderr) || firstLine(refreshed.stdout)})`)
        return
      }
    }
    const keys = Object.keys(installed).filter((key) => key.endsWith(`@${m.name}`) && enabled.has(key) && installed[key]?.some((r) => r.scope === 'user'))
    const manifests = await cloneManifests(m, io.read)
    // A plugin whose version the clone does not tell (one from a url) is
    // updated when the head moved, as every plugin once was.
    const behind = keys.filter((key) => {
      const version = manifests.get(key)?.version
      return version === undefined ? isMoved : installed[key]?.find((r) => r.scope === 'user')?.version !== version
    })
    const dependencies = async (key: string) => manifests.get(key)?.dependencies ?? []
    // Every plugin the chains reach, so a dependency's own new dependency is
    // installed too; in the order they are reached.
    const reached = new Set<string>()
    const reach = (key: string) => {
      for (const dependency of manifests.get(key)?.dependencies ?? []) {
        if (!reached.has(dependency)) {
          reached.add(dependency)
          reach(dependency)
        }
      }
    }
    keys.forEach(reach)
    const missing = [...reached].filter((key) => !isInstalledIn(installed, key))
    const failed = new Set<string>()
    for (const key of missing) {
      await mark()
      const added = await io.run(['claude', 'plugin', 'install', key, '--scope', 'user'], PLUGIN_COMMAND_MS)
      if (added.exitCode !== 0) {
        failed.add(key)
        io.log(`reload: ${key}, which ${m.name}'s plugins depend on, did not install (${lastLine(added.stderr) || lastLine(added.stdout) || `exit ${added.exitCode}`}); a later fetch tries again`)
      } else {
        io.log(`reload: ${key}: installed, as ${m.name}'s plugins depend on it`)
      }
    }
    const held = new Map<string, string>()
    for (const key of behind) {
      const reaches = await missingInChain(key, dependencies, (dependency) => failed.has(dependency))
      if (reaches !== undefined) {
        held.set(key, reaches)
      }
    }
    if (held.size > 0) {
      io.log(`reload: ${[...held.keys()].join(', ')}: held back, as ${[...new Set(held.values())].join(', ')} did not install`)
    }
    for (const key of behind.filter((k) => !held.has(k))) {
      await mark()
      const updated = await io.run(['claude', 'plugin', 'update', key, '--scope', 'user'], PLUGIN_COMMAND_MS)
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
      if (isMarked) {
        isMarked = false
        await io.run(['rm', '-f', '--', applying], 5_000)
      }
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

/** A row's text blocks, joined. */
const textOf = (content: readonly unknown[]) =>
  content.map((b) => (isRecord(b) && b.type === 'text' && typeof b.text === 'string' ? b.text : '')).join('')

/**
 * Which row of a `/reload-plugins` this plugin ran a `command`-door row is.
 * The engine keeps and sends a local command's three rows (2.1.302): the
 * caveat and the command line, from the origin of the plugin that ran it,
 * then the output, a `local_command` notice from the engine's, so known by
 * following the command line (`isOutputDue`). A caveat from this plugin is
 * this command's: its other run, /kairos, asks the model and gets none.
 */
export function reloadRow(
  message: { type: string; name?: string; content: readonly unknown[] },
  origin: unknown,
  self: string,
  isOutputDue: boolean,
): 'caveat' | 'command' | 'output' | undefined {
  if (message.type === 'system') {
    return isOutputDue && message.name === 'local_command' ? 'output' : undefined
  }
  if (!isRecord(origin) || origin.kind !== 'plugin' || origin.name !== self) {
    return undefined
  }
  const line = textOf(message.content)
  if (line.startsWith('<local-command-caveat>')) {
    return 'caveat'
  }
  return line.startsWith('<command-name>/reload-plugins</command-name>') ? 'command' : undefined
}

/** The output row's text without its tag: `Reloaded: N plugins · …`, or the error. */
export function outputText(content: readonly unknown[]): string {
  return textOf(content)
    .replace(/^<local-command-(?:stdout|stderr)>([\s\S]*)<\/local-command-(?:stdout|stderr)>$/, '$1')
    .trim()
}

/**
 * The sminos plugin's ask snapshot (its types/sminos.d.ts), whose
 * `isDialogUp` the reload waits on: the module that raised an ask's dialog
 * takes its answer. Never written where sminos is not loaded.
 */
const ASK = { plugin: 'sminos', key: 'ask' } as const

/** What the reloader's idle check reads, kept current by hooks (the check is synchronous). */
let isDialogUp = false
let isTurnRunning = false

/** Whether an ask's dialog is up, as sminos's snapshot last said. */
export const isAskDialogUp = () => isDialogUp
/** Whether a main-conversation turn is running: a slash command run now waits for its end. */
export const isMainTurnRunning = () => isTurnRunning

/** Forgets what the hooks read; for tests, which share this module. */
export function resetReload() {
  isDialogUp = false
  isTurnRunning = false
}

const dialogUpIn = (value: unknown) => isRecord(value) && value.isDialogUp === true

/**
 * Registers the watch and the fetch, in interactive sessions only: headless
 * runs refuse a plugin's `/reload-plugins`. `DOPERPOWERS_AUTORELOAD=off` (or
 * 0, false) leaves a launch on the versions it loaded and fetches nothing.
 * And the hook that keeps a reload's rows from the model, wherever one runs.
 */
export function registerReload(on: On) {
  // The ask's dialog, mirrored from each write of sminos's snapshot; seeded
  // at the session start below, so a reload of this plugin alone does not
  // miss a dialog already up.
  on('state.set', { plugin: 'sminos', key: 'ask' }, (_, e, next) => {
    isDialogUp = dialogUpIn(e.value)
    return next(e)
  })
  // The main turn, the engine's own (compact.tsx holds the module's
  // unmatched turn.start; a turn's id is never empty). A subagent's run
  // raises its own, with its agentId. Registered ahead of compact
  // (register.tsx), so its end comes after the compaction compact runs at
  // the turn's end.
  on('turn.start', { turnId: /./ }, (_, e, next) => {
    if (e.agentId === undefined) {
      isTurnRunning = true
    }
    return next(e)
  })
  on('turn.complete', { turnId: /./ }, async (_, e, next) => {
    try {
      return await next(e)
    } finally {
      if (e.agentId === undefined) {
        isTurnRunning = false
      }
    }
  })

  // The reload's rows, emptied: none can be refused, and each is kept and
  // sent as `(no content)`, which the screen does not draw. The output's
  // text goes to the person outside every request: a reload that says no
  // more than `Reloaded: …` as a toast (the debug log keeps it), anything
  // more (load errors, an unreachable marketplace, an update not applied) as
  // this plugin's transcript line. A transcript line is a system row the
  // engine draws through no render hook, so no view can fold it once drawn,
  // and a resume draws it again; a system row `$.session.append` makes is
  // drawn only in the transcript view (its level is `info`).
  let isOutputDue = false
  on('session.append', { door: 'command' }, async ($, e, next) => {
    const row = reloadRow(e.message, e.origin, $.plugin.name, isOutputDue)
    isOutputDue = row === 'command'
    if (row === undefined) {
      return next(e)
    }
    const stored = await next({ ...e, message: { ...e.message, content: [] } })
    if (row === 'output') {
      const text = `/reload-plugins: ${outputText(e.message.content)}`
      if (/^\/reload-plugins: Reloaded: [^\n]*$/.test(text)) {
        $.ui.toast(text, { timeoutMs: 8000 })
      } else {
        $.ui.log(text)
      }
    }
    return stored
  })

  on('session.start', { isInteractive: true }, async ($, e, next) => {
    const result = await next(e)
    try {
      isDialogUp = dialogUpIn((await $.state.get(ASK)).value)
    } catch (error) {
      $.ui.log(`reload: the ask's dialog could not be read: ${message(error)}`, { to: 'debug' })
    }
    const off = await $.env.get('DOPERPOWERS_AUTORELOAD')
    if (off === 'off' || off === '0' || off === 'false') {
      return result
    }
    const config = (await $.env.get('CLAUDE_CONFIG_DIR')) ?? `${await $.env.get('HOME')}/.claude`
    const plugins = `${config}/plugins`
    const fetchState = `${config}/autoreload`
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
      { plugins, state: fetchState },
    )
    const reloader = createReloader(
      {
        stat: (path) => $.fs.stat(path),
        read: (path) => $.fs.read(path),
        exists: (path) => $.fs.exists(path),
        enabled,
        reload: () => $.command.run({ command: 'reload-plugins' }),
        isAskDialogUp,
        isTurnRunning: isMainTurnRunning,
        now: () => Date.now(),
        toast: (line) => $.ui.toast(line, { timeoutMs: 8000 }),
        log: (line, to) => $.ui.log(line, { to }),
      },
      { file: `${plugins}/installed_plugins.json`, cacheDir: `${plugins}/cache`, fetchState, cwd: e.cwd, self: { name: $.plugin.name, root: $.plugin.root } },
    )
    void reloader.start().then(
      () => $.clock.every(POLL_MS, () => void reloader.tick()),
      (error) => $.ui.log(`reload: not watching plugin updates: ${message(error)}`, { to: 'debug' }),
    )
    $.clock.every(FETCH_LOOK_MS, () => void fetcher.tick())
    return result
  })
}
