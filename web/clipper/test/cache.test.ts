import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, readdir, readFile, utimes, stat } from 'node:fs/promises'
import { tmpdir, homedir } from 'node:os'
import { join } from 'node:path'
import { cacheRoot, generationName, currentGeneration, readFresh, beginBuild, publish, prune } from '../src/cache.ts'

const tmp = () => mkdtemp(join(tmpdir(), 'clip-cache-'))

async function build(entry: string, fetchedAt: Date, opts: { now?: () => Date; rand?: () => string } = {}) {
  const t = await beginBuild(entry)
  await writeFile(join(t, 'page.md'), 'hello\n')
  return publish(t, entry, async dir => {
    await writeFile(join(t, 'meta.json'),JSON.stringify({ ok: true, dir, file: join(dir, 'page.md'), fetchedAt: fetchedAt.toISOString() }))
  }, opts)
}

test('the cache root is --cache-dir, else WEB_CACHE_DIR, else XDG_CACHE_HOME/claude-web, else ~/.cache/claude-web', () => {
  assert.equal(cacheRoot('/a', { WEB_CACHE_DIR: '/b' }), '/a')
  assert.equal(cacheRoot(undefined, { WEB_CACHE_DIR: '/b', XDG_CACHE_HOME: '/x' }), '/b')
  assert.equal(cacheRoot(undefined, { XDG_CACHE_HOME: '/x' }), '/x/claude-web')
  assert.equal(cacheRoot(undefined, {}), join(homedir(), '.cache', 'claude-web'))
})

test('a relative cache root, from the option or the environment, is made absolute', () => {
  assert.equal(cacheRoot('clips', {}), join(process.cwd(), 'clips'))
  assert.equal(cacheRoot(undefined, { WEB_CACHE_DIR: 'rel/web' }), join(process.cwd(), 'rel', 'web'))
  assert.equal(cacheRoot(undefined, { XDG_CACHE_HOME: 'xdg' }), join(process.cwd(), 'xdg', 'claude-web'))
})

test('generation names carry the UTC time to the millisecond and a random suffix', () => {
  assert.equal(generationName(new Date('2026-10-25T10:15:30.042Z'), 'a1f3'), '20261025T101530042Z-a1f3')
})

test('a published generation holds meta.json whose paths name it, and the build folder is gone', async () => {
  const entry = join(await tmp(), 'host', 'slug-12345678')
  const dir = await build(entry, new Date())
  const names = await readdir(entry)
  assert.deepEqual(names, [dir.split('/').pop()])
  const meta = JSON.parse(await readFile(join(dir, 'meta.json'), 'utf8'))
  assert.equal(meta.dir, dir)
  assert.equal(currentGeneration(entry), dir)
})

test('a refresh publishes a new generation, and the older one stays readable at its path', async () => {
  const entry = join(await tmp(), 'h', 'e')
  const first = await build(entry, new Date(), { now: () => new Date('2026-10-25T10:15:30.005Z') })
  const second = await build(entry, new Date(), { now: () => new Date('2026-10-25T10:15:30.006Z') })
  assert.notEqual(first, second)
  assert.equal(currentGeneration(entry), second)
  assert.equal(await readFile(join(first, 'page.md'), 'utf8'), 'hello\n')
})

test('two refreshes in the same second whose random suffixes sort in reverse leave the later one current', async () => {
  const entry = join(await tmp(), 'h', 'e')
  const earlier = await build(entry, new Date(), { now: () => new Date('2026-10-25T10:15:30.005Z'), rand: () => 'ffff' })
  const later = await build(entry, new Date(), { now: () => new Date('2026-10-25T10:15:30.009Z'), rand: () => '0000' })
  assert.ok(earlier.endsWith('-ffff') && later.endsWith('-0000'))
  assert.equal(currentGeneration(entry), later)
})

test('a name taken by another publish is not overwritten: the publish picks a new name', async () => {
  const entry = join(await tmp(), 'h', 'e')
  const fixed = () => new Date('2026-10-25T10:15:30.005Z')
  const a = await build(entry, new Date(), { now: fixed, rand: () => 'abcd' })
  let calls = 0
  const b = await build(entry, new Date(), { now: fixed, rand: () => (calls++ === 0 ? 'abcd' : 'abce') })
  assert.ok(a.endsWith('-abcd') && b.endsWith('-abce'))
  const metaA = JSON.parse(await readFile(join(a, 'meta.json'), 'utf8'))
  const metaB = JSON.parse(await readFile(join(b, 'meta.json'), 'utf8'))
  assert.equal(metaA.dir, a)
  assert.equal(metaB.dir, b)
})

test('two concurrent publishes both complete, and the newer is current', async () => {
  const entry = join(await tmp(), 'h', 'e')
  const [a, b] = await Promise.all([build(entry, new Date()), build(entry, new Date())])
  const gens = (await readdir(entry)).sort()
  assert.equal(gens.length, 2)
  for (const d of [a, b]) JSON.parse(await readFile(join(d, 'meta.json'), 'utf8'))
  assert.equal(currentGeneration(entry), join(entry, gens[1]))
})

test('reuse answers from a generation under 24 hours old, and not from an older one or a .tmp- folder', async () => {
  const entry = join(await tmp(), 'h', 'e')
  assert.equal(await readFresh(entry, 24 * 3600e3), null)
  // Each generation is named by its own fetch time: two builds published in the
  // same millisecond would otherwise be ordered by their random suffixes.
  const old = new Date(Date.now() - 25 * 3600e3)
  await build(entry, old, { now: () => old })
  assert.equal(await readFresh(entry, 24 * 3600e3), null)
  const recent = new Date(Date.now() - 3600e3)
  const dir = await build(entry, recent, { now: () => recent })
  // An interrupted build: a .tmp- folder newer than anything, with files in it.
  const t = await beginBuild(entry)
  await writeFile(join(t, 'page.md'), 'partial')
  const meta = await readFresh<{ fetchedAt: string; dir: string }>(entry, 24 * 3600e3)
  assert.equal(meta?.dir, dir)
})

test('prune deletes old generations, stale .tmp- folders and empty entries, keeps the rest, and stamps .pruned', async () => {
  const root = await tmp()
  const oldEntry = join(root, 'a.example', 'old-11111111')
  const liveEntry = join(root, 'b.example', 'live-22222222')
  await build(oldEntry, new Date(Date.now() - 8 * 86400e3))
  const oldGen = await build(liveEntry, new Date(Date.now() - 9 * 86400e3))
  const freshGen = await build(liveEntry, new Date(Date.now() - 86400e3))
  const staleTmp = await beginBuild(liveEntry)
  const hourAgo = new Date(Date.now() - 2 * 3600e3)
  await utimes(staleTmp, hourAgo, hourAgo)
  const activeTmp = await beginBuild(liveEntry)
  await writeFile(join(root, 'usage.jsonl'), '{}\n')

  const { removed } = await prune(root, { olderThanDays: 7 })
  assert.equal(removed, 3)
  const left = (await readdir(liveEntry)).sort()
  assert.deepEqual(left, [activeTmp.split('/').pop(), freshGen.split('/').pop()].sort())
  await assert.rejects(stat(oldGen))
  await assert.rejects(stat(join(root, 'a.example')))
  assert.ok((await stat(join(root, '.pruned'))).isFile())
  assert.ok((await stat(join(root, 'usage.jsonl'))).isFile())
})

test('prune of a missing root removes nothing', async () => {
  const root = join(await tmp(), 'absent')
  assert.deepEqual(await prune(root, { olderThanDays: 7 }), { removed: 0 })
  await mkdir(root, { recursive: true })
})
