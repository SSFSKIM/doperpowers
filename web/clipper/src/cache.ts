// The cache: one entry folder per requested URL, one generation folder per
// fetch. A generation is built in a .tmp- folder and published by renaming it
// to a name that never existed, so readers see only complete generations and a
// refresh never replaces one another agent may be reading.
import { randomBytes } from 'node:crypto'
import { readdirSync } from 'node:fs'
import { mkdir, mkdtemp, readFile, readdir, rename, rm, rmdir, stat, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { join } from 'node:path'

export const REUSE_MAX_AGE_MS = 24 * 3600e3
const TMP_PREFIX = '.tmp-'
const TMP_STALE_MS = 3600e3

export function cacheRoot(option: string | undefined, env: NodeJS.ProcessEnv = process.env): string {
  if (option) return option
  if (env.WEB_CACHE_DIR) return env.WEB_CACHE_DIR
  return join(env.XDG_CACHE_HOME || join(homedir(), '.cache'), 'claude-web')
}

/** `<UTC yyyymmddThhmmssSSSZ>-<4 hex>`: names sort in publishing order. */
export function generationName(now: Date, rand: string): string {
  return now.toISOString().replace(/[-:]/g, '').replace('.', '') + '-' + rand
}

const isGeneration = (name: string) => !name.startsWith('.')

/** The entry's current generation folder: the newest published one. */
export function currentGeneration(entry: string): string | null {
  let names: string[]
  try { names = readdirSync(entry) } catch { return null }
  const gens = names.filter(isGeneration).sort()
  return gens.length ? join(entry, gens[gens.length - 1]) : null
}

/** The current generation's meta.json, when it was fetched under `maxAgeMs` ago. */
export async function readFresh<T extends { fetchedAt: string }>(entry: string, maxAgeMs: number, now = Date.now()): Promise<T | null> {
  const gen = currentGeneration(entry)
  if (!gen) return null
  try {
    const meta = JSON.parse(await readFile(join(gen, 'meta.json'), 'utf8')) as T
    const age = now - Date.parse(meta.fetchedAt)
    return age >= 0 && age < maxAgeMs ? meta : null
  } catch {
    return null
  }
}

export async function beginBuild(entry: string): Promise<string> {
  await mkdir(entry, { recursive: true })
  return mkdtemp(join(entry, TMP_PREFIX))
}

export type PublishOptions = { now?: () => Date; rand?: () => string }

/**
 * Publishes the build folder as a new generation and returns its path.
 * `writeMeta` writes meta.json into the build folder last, given the final
 * path, which the name fixes just before the rename.
 */
export async function publish(tmp: string, entry: string, writeMeta: (finalDir: string) => Promise<void>, opts: PublishOptions = {}): Promise<string> {
  const now = opts.now ?? (() => new Date())
  const rand = opts.rand ?? (() => randomBytes(2).toString('hex'))
  for (let attempt = 0; ; attempt++) {
    const dir = join(entry, generationName(now(), rand()))
    await writeMeta(dir)
    try {
      await rename(tmp, dir)
      return dir
    } catch (e) {
      const code = (e as NodeJS.ErrnoException).code
      if ((code !== 'ENOTEMPTY' && code !== 'EEXIST') || attempt >= 5) throw e
    }
  }
}

/** Deletes generations fetched over `olderThanDays` ago, stale .tmp- folders, and folders left empty. */
export async function prune(root: string, opts: { olderThanDays: number; now?: number }): Promise<{ removed: number }> {
  const now = opts.now ?? Date.now()
  const maxAge = opts.olderThanDays * 86400e3
  let removed = 0
  for (const host of await dirs(root)) {
    const hostDir = join(root, host)
    for (const entry of await dirs(hostDir)) {
      const entryDir = join(hostDir, entry)
      for (const name of await dirs(entryDir)) {
        const dir = join(entryDir, name)
        if (name.startsWith(TMP_PREFIX) ? now - (await stat(dir)).mtimeMs > TMP_STALE_MS : now - (await fetchedAt(dir)) > maxAge) {
          await rm(dir, { recursive: true, force: true })
          removed++
        }
      }
      await rmdir(entryDir).catch(() => {})
    }
    await rmdir(hostDir).catch(() => {})
  }
  // The stamp the mod reads to start the next prune; a missing root has nothing to stamp.
  await writeFile(join(root, '.pruned'), new Date(now).toISOString() + '\n').catch(() => {})
  return { removed }
}

async function dirs(path: string): Promise<string[]> {
  try {
    return (await readdir(path, { withFileTypes: true })).filter(d => d.isDirectory()).map(d => d.name)
  } catch {
    return []
  }
}

async function fetchedAt(gen: string): Promise<number> {
  try {
    const t = Date.parse(JSON.parse(await readFile(join(gen, 'meta.json'), 'utf8')).fetchedAt)
    if (!Number.isNaN(t)) return t
  } catch {}
  return (await stat(gen)).mtimeMs
}
